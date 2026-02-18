from __future__ import annotations

import base64
import json
import logging
import mimetypes
from dataclasses import dataclass, field
from typing import Any, TypeVar, cast

import litellm
from litellm.exceptions import APIError
from litellm.types.utils import ModelResponse
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

BatchResults = dict[str, T]


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


class LLMClient:
    def __init__(self, model: str, api_key: str) -> None:
        self._model = model
        self._api_key = api_key
        self._results_cache: dict[str, dict[str, str]] = {}

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
                    "type": "json_object",
                    "response_schema": item.response_schema,
                },
            ),
        )

        text = response.choices[0].message.content  # type: ignore[union-attr]
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
        raw: dict[str, str] = {}
        for item in prompts:
            try:
                _, text = self._complete_one(item)
                raw[item.item_id] = text
                logger.info("Generated %s", item.item_id)
            except Exception:
                logger.error(
                    "Generation failed for %s",
                    item.item_id,
                    exc_info=True,
                )

        self._results_cache[batch_id] = raw
        logger.info(
            "Completed %d/%d prompts for batch %s",
            len(raw),
            len(prompts),
            batch_id,
        )
        return batch_id

    def batch_get_results(
        self,
        job_key: str,
        schema: type[T],
    ) -> BatchResults[T] | None:
        raw = self._results_cache.pop(job_key, None)
        if raw is None:
            return None

        results: BatchResults[T] = {}
        for item_id, text in raw.items():
            try:
                parsed = json.loads(text)
                results[item_id] = schema.model_validate(parsed)
            except Exception:
                logger.error(
                    "Failed to parse result for %s: %.200s",
                    item_id,
                    text,
                    exc_info=True,
                )

        return results
