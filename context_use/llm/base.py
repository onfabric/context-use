from __future__ import annotations

import base64
import json
import logging
import mimetypes
import tempfile
from dataclasses import dataclass, field
from typing import Any, TypeVar

import litellm
from pydantic import BaseModel

from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

BatchResults = dict[str, T]
EmbedBatchResults = dict[str, list[float]]

AvailableLlmModels = OpenAIModel
AvailableEmbeddingModels = OpenAIEmbeddingModel

_BATCH_TERMINAL_STATES: set[str] = {"failed", "cancelled", "expired"}


@dataclass
class PromptItem:
    """A single prompt to send to the LLM.

    Attributes:
        item_id:         Unique key for this item (thread_id, date string, etc.)
        prompt:          The text prompt.
        response_schema: JSON schema dict the LLM should conform to.
        asset_paths:     Local file paths for images/videos to include as parts.
    """

    item_id: str
    prompt: str
    response_schema: dict
    asset_paths: list[str] = field(default_factory=list)


@dataclass
class EmbedItem:
    """A single text to embed.

    Attributes:
        item_id: Unique key (e.g. memory UUID).
        text:    The text to embed.
    """

    item_id: str
    text: str


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
        parts.append(
            {"type": "image_url", "image_url": {"url": _encode_file_as_data_url(path)}}
        )
    parts.append({"type": "text", "text": item.prompt})
    return [{"role": "user", "content": parts}]


def _build_batch_jsonl_line(
    item: PromptItem,
    model: AvailableLlmModels,
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
    model: AvailableEmbeddingModels,
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


class LLMClient:
    def __init__(
        self,
        model: AvailableLlmModels,
        api_key: str,
        embedding_model: AvailableEmbeddingModels,
    ) -> None:
        self._model = model
        self._embedding_model = embedding_model
        self._api_key = api_key

    async def batch_submit(
        self,
        batch_id: str,
        prompts: list[PromptItem],
    ) -> str:
        """Build JSONL, upload to OpenAI, and create a batch job.

        Returns the OpenAI batch ID for polling with ``batch_get_results``.
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

    async def batch_get_results(
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

        return self._parse_batch_results(content.content, schema)

    def _parse_batch_results(
        self,
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

    async def completion(self, prompt: str) -> str:
        """Run a single chat completion and return the text response."""
        response = await litellm.acompletion(
            model=self._model.value,
            messages=[{"role": "user", "content": prompt}],
            api_key=self._api_key,
        )
        text: str = response.choices[0].message.content  # type: ignore[union-attr]
        return text.strip()

    async def embed_batch_submit(
        self,
        batch_id: str,
        items: list[EmbedItem],
    ) -> str:
        """Build embedding JSONL, upload, and create a batch job.

        Returns the OpenAI batch ID for polling with
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

        return self._parse_embed_batch_results(content.content)

    def _parse_embed_batch_results(
        self,
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
