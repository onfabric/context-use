from __future__ import annotations

import base64
import json
import logging
import mimetypes
import tempfile
from typing import Any

import litellm
from pydantic import BaseModel

from context_use.llm.base import (
    BaseLLMClient,
    BatchResults,
    EmbedBatchResults,
    EmbedItem,
    PromptItem,
)
from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel

logger = logging.getLogger(__name__)


def _encode_file_as_data_url(path: str) -> str:
    mime_type, _ = mimetypes.guess_type(path)
    mime_type = mime_type or "application/octet-stream"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime_type};base64,{b64}"


def _build_response_format(item: PromptItem) -> dict:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "response",
            "schema": item.response_schema,
        },
    }


def _build_messages(item: PromptItem) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = []
    for path in item.asset_paths:
        try:
            data_url = _encode_file_as_data_url(path)
        except FileNotFoundError:
            logger.warning("Skipping missing asset: %s", path)
            continue
        parts.append({"type": "image_url", "image_url": {"url": data_url}})
    parts.append({"type": "text", "text": item.prompt})
    return [{"role": "user", "content": parts}]


class _LiteLLMBase(BaseLLMClient):
    """Shared init, completion, and embed_query for litellm-backed clients."""

    def __init__(
        self,
        model: OpenAIModel,
        api_key: str,
        embedding_model: OpenAIEmbeddingModel,
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        self._api_key = api_key

    async def completion(self, prompt: str) -> str:
        response = await litellm.acompletion(
            model=self._model.value,
            messages=[{"role": "user", "content": prompt}],
            api_key=self._api_key,
        )
        text: str = response.choices[0].message.content  # type: ignore[union-attr]
        return text.strip()

    async def embed_query(self, text: str) -> list[float]:
        response = await litellm.aembedding(
            model=self._embedding_model.value,
            input=[text],
            api_key=self._api_key,
        )
        return response.data[0]["embedding"]


_BATCH_TERMINAL_STATES: set[str] = {"failed", "cancelled", "expired"}


def _build_batch_jsonl_line(
    item: PromptItem,
    model: OpenAIModel,
) -> dict[str, Any]:
    model_name = model.value.split("/", 1)[-1]
    return {
        "custom_id": item.item_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model_name,
            "messages": _build_messages(item),
            "response_format": _build_response_format(item),
        },
    }


def _build_embed_batch_jsonl_line(
    item: EmbedItem,
    model: OpenAIEmbeddingModel,
) -> dict[str, Any]:
    model_name = model.value.split("/", 1)[-1]
    return {
        "custom_id": item.item_id,
        "method": "POST",
        "url": "/v1/embeddings",
        "body": {
            "model": model_name,
            "input": item.text,
        },
    }


def _parse_batch_results[T: BaseModel](
    raw: bytes,
    schema: type[T],
) -> BatchResults[T]:
    results: BatchResults[T] = {}
    for line in raw.decode("utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            custom_id: str | None = data.get("custom_id")
            text: str = (
                data.get("response", {})
                .get("body", {})
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            if not custom_id or not text:
                logger.warning("Skipping result line with missing id or content")
                continue
            parsed = json.loads(text)
            results[custom_id] = schema.model_validate(parsed)
        except Exception:
            logger.error(
                "Failed to parse batch result line: %.200s",
                line,
                exc_info=True,
            )

    return results


def _parse_embed_batch_results(
    raw: bytes,
) -> EmbedBatchResults:
    results: EmbedBatchResults = {}
    for line in raw.decode("utf-8").strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            custom_id: str | None = data.get("custom_id")
            embedding_data: list[dict] = (
                data.get("response", {}).get("body", {}).get("data", [])
            )
            if not custom_id or not embedding_data:
                logger.warning("Skipping embed result line with missing id or data")
                continue
            results[custom_id] = embedding_data[0]["embedding"]
        except Exception:
            logger.error(
                "Failed to parse embed batch result line: %.200s",
                line,
                exc_info=True,
            )

    return results


class LiteLLMBatchClient(_LiteLLMBase):
    """OpenAI-compatible batch client using JSONL file upload and polling."""

    async def batch_submit(
        self,
        batch_id: str,
        prompts: list[PromptItem],
    ) -> str:
        """Build JSONL, upload to OpenAI, and create a batch job.

        Returns the provider batch ID for polling with ``batch_get_results``.
        """
        lines: list[str] = []
        for item in prompts:
            line = _build_batch_jsonl_line(item, self._model)
            lines.append(json.dumps(line))

        jsonl_bytes = "\n".join(lines).encode("utf-8")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=True) as tmp:
            tmp.write(jsonl_bytes)
            tmp.flush()
            tmp.seek(0)

            file_obj = await litellm.acreate_file(
                file=(f"batch-{batch_id}.jsonl", tmp, "application/jsonl"),
                purpose="batch",
                custom_llm_provider="openai",
                api_key=self._api_key,
            )

        logger.info(
            "Uploaded batch file %s (%d prompts) for batch %s",
            file_obj.id,
            len(prompts),
            batch_id,
        )

        batch = await litellm.acreate_batch(
            completion_window="24h",
            endpoint="/v1/chat/completions",
            input_file_id=file_obj.id,
            custom_llm_provider="openai",
            api_key=self._api_key,
        )

        logger.info(
            "Created batch job %s for batch %s (%d prompts)",
            batch.id,
            batch_id,
            len(prompts),
        )
        return batch.id

    async def batch_get_results[T: BaseModel](
        self,
        job_key: str,
        schema: type[T],
    ) -> BatchResults[T] | None:
        """Poll an OpenAI batch job for results.

        Returns ``None`` while the job is still running, parsed
        ``BatchResults`` when complete, or raises on terminal failure.
        """
        batch = await litellm.aretrieve_batch(
            batch_id=job_key,
            custom_llm_provider="openai",
            api_key=self._api_key,
        )

        if batch.status in _BATCH_TERMINAL_STATES:
            raise RuntimeError(f"Batch {job_key} ended with status {batch.status}")

        if batch.status != "completed" or not batch.output_file_id:
            return None

        content = await litellm.afile_content(
            file_id=batch.output_file_id,
            custom_llm_provider="openai",
            api_key=self._api_key,
        )

        return _parse_batch_results(content.content, schema)

    async def embed_batch_submit(
        self,
        batch_id: str,
        items: list[EmbedItem],
    ) -> str:
        """Build embedding JSONL, upload, and create a batch job.

        Returns the provider batch ID for polling with
        ``embed_batch_get_results``.
        """
        lines = [
            json.dumps(_build_embed_batch_jsonl_line(item, self._embedding_model))
            for item in items
        ]
        jsonl_bytes = "\n".join(lines).encode("utf-8")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=True) as tmp:
            tmp.write(jsonl_bytes)
            tmp.flush()
            tmp.seek(0)

            file_obj = await litellm.acreate_file(
                file=(
                    f"embed-batch-{batch_id}.jsonl",
                    tmp,
                    "application/jsonl",
                ),
                purpose="batch",
                custom_llm_provider="openai",
                api_key=self._api_key,
            )

        logger.info(
            "Uploaded embed batch file %s (%d items) for batch %s",
            file_obj.id,
            len(items),
            batch_id,
        )

        batch = await litellm.acreate_batch(
            completion_window="24h",
            endpoint="/v1/embeddings",
            input_file_id=file_obj.id,
            custom_llm_provider="openai",
            api_key=self._api_key,
        )

        logger.info(
            "Created embed batch job %s for batch %s (%d items)",
            batch.id,
            batch_id,
            len(items),
        )
        return batch.id

    async def embed_batch_get_results(
        self,
        job_key: str,
    ) -> EmbedBatchResults | None:
        """Poll an OpenAI embedding batch job.

        Returns ``None`` while still running, or a dict mapping each
        ``item_id`` to its embedding vector.
        """
        batch = await litellm.aretrieve_batch(
            batch_id=job_key,
            custom_llm_provider="openai",
            api_key=self._api_key,
        )

        if batch.status in _BATCH_TERMINAL_STATES:
            raise RuntimeError(
                f"Embed batch {job_key} ended with status {batch.status}"
            )

        if batch.status != "completed" or not batch.output_file_id:
            return None

        content = await litellm.afile_content(
            file_id=batch.output_file_id,
            custom_llm_provider="openai",
            api_key=self._api_key,
        )

        return _parse_embed_batch_results(content.content)


class LiteLLMSyncClient(_LiteLLMBase):
    """Runs all prompts via individual completions (no batch API).

    Useful for quickstart / demos where the batch API's latency
    (minutes) is unacceptable.  Implements the same submit/poll
    interface so the state machine works unchanged — ``batch_submit``
    does all the work eagerly and ``batch_get_results`` returns the
    cached results immediately.
    """

    def __init__(
        self,
        model: OpenAIModel,
        api_key: str,
        embedding_model: OpenAIEmbeddingModel,
    ) -> None:
        super().__init__(model, api_key, embedding_model)
        self._gen_cache: dict[str, BatchResults] = {}  # type: ignore[type-arg]
        self._embed_cache: dict[str, EmbedBatchResults] = {}

    async def batch_submit(
        self,
        batch_id: str,
        prompts: list[PromptItem],
    ) -> str:
        results: BatchResults = {}  # type: ignore[type-arg]
        for item in prompts:
            try:
                response = await litellm.acompletion(
                    model=self._model.value,
                    messages=_build_messages(item),
                    response_format=_build_response_format(item),
                    api_key=self._api_key,
                )
                text: str = response.choices[0].message.content  # type: ignore[union-attr]
                results[item.item_id] = json.loads(text.strip())
            except Exception:
                logger.error(
                    "Sync completion failed for %s: %.200s",
                    item.item_id,
                    item.prompt,
                    exc_info=True,
                )
        logger.info(
            "[%s] Completed %d/%d sync completions",
            batch_id,
            len(results),
            len(prompts),
        )
        key = f"gen-{batch_id}"
        self._gen_cache[key] = results
        return key

    async def batch_get_results[T: BaseModel](
        self,
        job_key: str,
        schema: type[T],
    ) -> BatchResults[T] | None:
        raw = self._gen_cache.pop(job_key, None)
        if raw is None:
            return None
        return {item_id: schema.model_validate(data) for item_id, data in raw.items()}

    async def embed_batch_submit(
        self,
        batch_id: str,
        items: list[EmbedItem],
    ) -> str:
        results: EmbedBatchResults = {}
        for item in items:
            try:
                response = await litellm.aembedding(
                    model=self._embedding_model.value,
                    input=[item.text],
                    api_key=self._api_key,
                )
                results[item.item_id] = response.data[0]["embedding"]
            except Exception:
                logger.error(
                    "Sync embedding failed for %s",
                    item.item_id,
                    exc_info=True,
                )
        logger.info(
            "[%s] Completed %d/%d sync embeddings",
            batch_id,
            len(results),
            len(items),
        )
        key = f"embed-{batch_id}"
        self._embed_cache[key] = results
        return key

    async def embed_batch_get_results(
        self,
        job_key: str,
    ) -> EmbedBatchResults | None:
        return self._embed_cache.pop(job_key, None)
