"""Gemini client using the real-time API with File API for local assets."""

from __future__ import annotations

import json
import logging
import mimetypes
import time
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from context_use.llm.base import BatchLLMClient, BatchResults, PromptItem

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

FILE_POLL_INTERVAL_SECS = 2
FILE_POLL_MAX_ATTEMPTS = 30
REQUEST_DELAY_SECS = 4.0


class GeminiClient(BatchLLMClient):
    """Gemini client that uploads local files and calls ``generate_content``.

    Parameters
    ----------
    genai_client:
        An authenticated ``google.genai.Client`` instance.
    model:
        Model name, e.g. ``"gemini-2.5-flash"``.
    """

    def __init__(
        self,
        genai_client: genai.Client,
        model: str = "gemini-2.5-flash",
    ) -> None:
        self._client = genai_client
        self._model = model
        self._results_cache: dict[str, dict[str, str]] = {}

    @retry(
        retry=retry_if_exception_type(genai_errors.APIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=3, max=30, jitter=3),
    )
    def _upload_file(self, path: str) -> genai.types.File:
        """Upload a local file and block until it reaches ACTIVE state."""
        mime_type, _ = mimetypes.guess_type(path)
        config = (
            genai.types.UploadFileConfig(mime_type=mime_type) if mime_type else None
        )
        return self._client.files.upload(file=path, config=config)

    def _upload_all(
        self, prompts: list[PromptItem]
    ) -> dict[str, list[genai.types.File]]:
        """Upload all assets for all prompts upfront.

        Returns ``{item_id: [uploaded_file, …]}``.
        """
        result: dict[str, list[genai.types.File]] = {}
        for item in prompts:
            files = []
            for path in item.asset_paths:
                logger.info("Uploading %s", path)
                files.append(self._upload_file(path))
            result[item.item_id] = files
        return result

    @retry(
        retry=retry_if_exception_type(genai_errors.APIError),
        stop=stop_after_attempt(5),
        wait=wait_exponential_jitter(initial=5, max=60, jitter=5),
    )
    def _generate_one(
        self,
        item: PromptItem,
        uploaded_files: list[genai.types.File],
    ) -> tuple[str, str]:
        """Call ``generate_content`` for one prompt item.

        Returns ``(item_id, raw_json_text)``.
        """
        contents: list = [*uploaded_files, item.prompt]

        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
            config={
                "response_mime_type": "application/json",
                "response_schema": item.response_schema,
            },
        )

        text = response.text
        if not text:
            raise ValueError(f"Empty response for item {item.item_id}")
        return item.item_id, text.strip()

    def batch_submit(
        self,
        batch_id: str,
        prompts: list[PromptItem],
    ) -> str:
        """Upload all assets once, then generate sequentially."""
        uploaded = self._upload_all(prompts)
        logger.info("All files uploaded for batch %s, generating…", batch_id)

        raw: dict[str, str] = {}
        for item in prompts:
            try:
                time.sleep(REQUEST_DELAY_SECS)
                _, text = self._generate_one(item, uploaded[item.item_id])
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
        """Return cached results parsed into *schema*."""
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
