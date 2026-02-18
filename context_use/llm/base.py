from __future__ import annotations

import base64
import json
import logging
import mimetypes
import tempfile
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast

import litellm
from litellm.batches.main import create_batch, retrieve_batch
from litellm.exceptions import APIError
from litellm.files.main import create_file, file_content
from litellm.types.llms.openai import HttpxBinaryResponseContent, OpenAIFileObject
from litellm.types.utils import Choices, LiteLLMBatch, ModelResponse
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from context_use.llm.models import OpenAIModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

BatchResults = dict[str, T]

AvailableLlmModels = OpenAIModel

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


def _encode_file_as_data_url(path: str) -> str:
    mime_type, _ = mimetypes.guess_type(path)
    mime_type = mime_type or "application/octet-stream"
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:{mime_type};base64,{b64}"


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
    model: str,
) -> dict[str, Any]:
    return {
        "custom_id": item.item_id,
        "method": "POST",
        "url": "/v1/chat/completions",
        "body": {
            "model": model,
            "messages": _build_messages(item),
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "response",
                    "schema": item.response_schema,
                },
            },
        },
    }


class LLMClient:
    def __init__(self, model: AvailableLlmModels, api_key: str) -> None:
        self._model = model.value
        self._api_key = api_key

    @property
    def _raw_model_name(self) -> str:
        return self._model.split("/", 1)[-1]

    @retry(
        retry=retry_if_exception_type(APIError),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=5, max=60, jitter=5),
    )
    def _complete_one(self, item: PromptItem) -> tuple[str, str]:
        """Call the LLM for a single prompt item.

        Returns ``(item_id, raw_json_text)``.
        """
        response = cast(
            ModelResponse,
            litellm.completion(
                model=self._model,
                api_key=self._api_key,
                messages=_build_messages(item),
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "response",
                        "schema": item.response_schema,
                    },
                },
            ),
        )

        choices = cast(list[Choices], response.choices)
        text = choices[0].message.content
        if not text:
            raise ValueError(f"Empty response for item {item.item_id}")
        return item.item_id, text.strip()

    def complete(
        self,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> ModelResponse:
        return cast(
            ModelResponse,
            litellm.completion(
                model=self._model,
                api_key=self._api_key,
                messages=messages,
                **kwargs,
            ),
        )

    def batch_submit(
        self,
        batch_id: str,
        prompts: list[PromptItem],
    ) -> str:
        """Build JSONL, upload to OpenAI, and create a batch job.

        Returns the OpenAI batch ID for polling with ``batch_get_results``.
        """
        lines: list[str] = []
        for item in prompts:
            line = _build_batch_jsonl_line(item, self._raw_model_name)
            lines.append(json.dumps(line))

        jsonl_bytes = "\n".join(lines).encode("utf-8")

        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=True) as tmp:
            tmp.write(jsonl_bytes)
            tmp.flush()
            tmp.seek(0)

            file_obj = cast(
                OpenAIFileObject,
                create_file(
                    file=(f"batch-{batch_id}.jsonl", tmp, "application/jsonl"),
                    purpose="batch",
                    custom_llm_provider="openai",
                    api_key=self._api_key,
                ),
            )

        logger.info(
            "Uploaded batch file %s (%d prompts) for batch %s",
            file_obj.id,
            len(prompts),
            batch_id,
        )

        batch = cast(
            LiteLLMBatch,
            create_batch(
                completion_window="24h",
                endpoint="/v1/chat/completions",
                input_file_id=file_obj.id,
                custom_llm_provider="openai",
                api_key=self._api_key,
            ),
        )

        logger.info(
            "Created batch job %s for batch %s (%d prompts)",
            batch.id,
            batch_id,
            len(prompts),
        )
        return batch.id

    def batch_get_results(
        self,
        job_key: str,
        schema: type[T],
    ) -> BatchResults[T] | None:
        """Poll an OpenAI batch job for results.

        Returns ``None`` while the job is still running, parsed
        ``BatchResults`` when complete, or raises on terminal failure.
        """
        batch = cast(
            LiteLLMBatch,
            retrieve_batch(
                batch_id=job_key,
                custom_llm_provider="openai",
                api_key=self._api_key,
            ),
        )

        if batch.status in _BATCH_TERMINAL_STATES:
            raise RuntimeError(f"Batch {job_key} ended with status {batch.status}")

        if batch.status != "completed" or not batch.output_file_id:
            return None

        content = cast(
            HttpxBinaryResponseContent,
            file_content(
                file_id=batch.output_file_id,
                custom_llm_provider="openai",
                api_key=self._api_key,
            ),
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
