"""Gemini client using the real-time API with File API for local assets."""

from __future__ import annotations

import json
import logging
import mimetypes
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import TypeVar

from google import genai
from google.genai import (
    errors as genai_errors,
)
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

MAX_WORKERS = 5


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

    def _upload_file(self, path: str) -> genai.types.File:
        """Upload a local file via the Gemini File API."""
        mime_type, _ = mimetypes.guess_type(path)
        config = {"mime_type": mime_type} if mime_type else None
        return self._client.files.upload(file=path, config=config)

    def _build_contents(self, item: PromptItem) -> list:
        """Build a multimodal contents list: uploaded files first, text last.

        The Gemini SDK auto-wraps a flat list into a single user turn,
        so ``[file1, file2, "text"]`` becomes one ``Content`` with three
        ``Part`` entries — matching the aertex ``_build_prompt_parts``
        pattern but for local files.
        """
        contents: list = []
        for path in item.asset_paths:
            contents.append(self._upload_file(path))
        contents.append(item.prompt)
        return contents

    @retry(
        retry=retry_if_exception_type(genai_errors.APIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
    )
    def _generate_one(self, item: PromptItem) -> tuple[str, str]:
        """Call ``generate_content`` for one prompt item.

        Returns ``(item_id, raw_json_text)``.
        """
        contents = self._build_contents(item)

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
        """Process all prompts concurrently and cache raw results."""
        raw: dict[str, str] = {}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {
                pool.submit(self._generate_one, item): item.item_id for item in prompts
            }
            for future in as_completed(futures):
                item_id = futures[future]
                try:
                    _, text = future.result()
                    raw[item_id] = text
                except Exception:
                    logger.error(
                        "Generation failed for %s",
                        item_id,
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
