"""Gemini client using the asynchronous Batch API with the File API."""

from __future__ import annotations

import json
import logging
import mimetypes
import tempfile
from typing import Any, TypeVar

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
from context_use.llm.gemini.batch.utils import (
    build_jsonl_content,
    create_batch_job,
    get_batch_job_status,
    parse_jsonl_results,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class GeminiBatchClient(BatchLLMClient):
    """Gemini client that submits work via the Batch API.

    Unlike :class:`GeminiClient` (real-time), this client:

    * Uploads assets via the Gemini File API
    * Builds a JSONL request file and uploads it via the File API
    * Creates a batch job via ``genai_client.batches.create()``
    * Polls for completion via ``genai_client.batches.get()``
    * Downloads result JSONL via ``genai_client.files.download()``

    No GCS bucket or ``google-cloud-storage`` dependency is required.

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
        self._uploaded_files: dict[str, list[str]] = {}

    @retry(
        retry=retry_if_exception_type(genai_errors.APIError),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=3, max=30, jitter=3),
    )
    def _upload_file(self, path: str) -> genai.types.File:
        """Upload a local file via the File API."""
        mime_type, _ = mimetypes.guess_type(path)
        config = (
            genai.types.UploadFileConfig(mime_type=mime_type) if mime_type else None
        )
        uploaded = self._client.files.upload(file=path, config=config)
        logger.info("Uploaded %s → %s", path, uploaded.name)
        return uploaded

    def _build_parts(
        self, item: PromptItem, file_names: list[str]
    ) -> list[dict[str, Any]]:
        """Build Gemini ``parts`` for one :class:`PromptItem`.

        Local files are uploaded via the File API and referenced as
        ``fileData`` entries inside the JSONL payload.  Uploaded file
        names are appended to *file_names* for later cleanup.
        """
        parts: list[dict[str, Any]] = []
        for path in item.asset_paths:
            uploaded = self._upload_file(path)
            if uploaded.name:
                file_names.append(uploaded.name)
            parts.append(
                {
                    "fileData": {
                        "fileUri": uploaded.uri,
                        "mimeType": uploaded.mime_type or "application/octet-stream",
                    }
                }
            )
        parts.append({"text": item.prompt})
        return parts

    def _build_request_line(
        self, item: PromptItem, file_names: list[str]
    ) -> dict[str, Any]:
        """Build one JSONL line for the Batch API."""
        parts = self._build_parts(item, file_names)
        return {
            "key": item.item_id,
            "request": {
                "contents": [{"parts": parts, "role": "user"}],
                "generation_config": {
                    "response_mime_type": "application/json",
                    "response_json_schema": item.response_schema,
                },
            },
        }

    def _upload_jsonl(self, content: bytes, display_name: str) -> genai.types.File:
        """Write *content* to a temp file, upload via the File API."""
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=True) as tmp:
            tmp.write(content)
            tmp.flush()
            config = genai.types.UploadFileConfig(
                mime_type="application/jsonl",
                display_name=display_name,
            )
            uploaded = self._client.files.upload(file=tmp.name, config=config)
        logger.info("Uploaded JSONL → %s", uploaded.name)
        return uploaded

    def batch_submit(
        self,
        batch_id: str,
        prompts: list[PromptItem],
    ) -> str:
        """Upload assets + JSONL via the File API, create a batch job."""
        file_names: list[str] = []
        requests: list[dict[str, Any]] = []
        for item in prompts:
            try:
                requests.append(self._build_request_line(item, file_names))
            except Exception:
                logger.error(
                    "Failed to build request for %s",
                    item.item_id,
                    exc_info=True,
                )

        jsonl_bytes = build_jsonl_content(requests)
        uploaded = self._upload_jsonl(jsonl_bytes, f"batch-{batch_id}")
        if not uploaded.name:
            raise RuntimeError("JSONL upload succeeded but returned no name")
        file_names.append(uploaded.name)

        job_name = create_batch_job(self._client, self._model, uploaded.name)
        self._uploaded_files[job_name] = file_names
        logger.info(
            "Submitted batch %s (%d prompts, %d files uploaded) → %s",
            batch_id,
            len(requests),
            len(file_names),
            job_name,
        )
        return job_name

    def _cleanup_files(self, job_key: str) -> None:
        """Delete all File API uploads associated with *job_key*."""
        names = self._uploaded_files.pop(job_key, [])
        for name in names:
            try:
                self._client.files.delete(name=name)
                logger.debug("Deleted uploaded file %s", name)
            except Exception:
                logger.warning(
                    "Failed to delete file %s (will auto-expire in 48h)",
                    name,
                    exc_info=True,
                )

    def batch_get_results(
        self,
        job_key: str,
        schema: type[T],
    ) -> BatchResults[T] | None:
        """Poll the batch job and return parsed results.

        When the job is finished (success or failure), all files uploaded
        for this job are deleted from the File API.
        """
        status = get_batch_job_status(self._client, job_key)

        if status.error:
            self._cleanup_files(job_key)
            raise RuntimeError(status.error)

        if status.dest_file is None:
            return None

        content: bytes = self._client.files.download(file=status.dest_file)
        self._cleanup_files(job_key)

        def _parse_line(
            data: dict[str, Any],
        ) -> tuple[str | None, T | None]:
            item_id = data.get("key")
            candidates = data.get("response", {}).get("candidates", [])
            if not item_id or not candidates:
                return None, None

            text = (
                candidates[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
                .strip()
            )
            if not text:
                logger.warning("Empty text for key %s", item_id)
                return None, None

            try:
                parsed = json.loads(text)
                return item_id, schema.model_validate(parsed)
            except Exception:
                logger.error(
                    "Failed to parse result for %s: %.200s",
                    item_id,
                    text,
                    exc_info=True,
                )
                return None, None

        raw = parse_jsonl_results(content, _parse_line)
        return raw
