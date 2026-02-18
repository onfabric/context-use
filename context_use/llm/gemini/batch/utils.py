"""JSONL and polling utilities for the Gemini Batch API."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from google import genai
from google.genai import errors as genai_errors
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from context_use.llm.gemini.batch.models import BatchJobResult, BatchJobState

logger = logging.getLogger(__name__)


def build_jsonl_content(requests: list[dict[str, Any]]) -> bytes:
    """Serialise a list of dicts into newline-delimited JSON bytes."""
    if not requests:
        raise ValueError("No requests provided for JSONL generation")
    return "\n".join(json.dumps(r) for r in requests).encode("utf-8")


@retry(
    retry=retry_if_exception_type(genai_errors.APIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
)
def create_batch_job(
    genai_client: genai.Client,
    model: str,
    src: str,
) -> str:
    """Create a Gemini batch job and return its ``name``.

    *src* is a File API resource name for the uploaded JSONL.
    """
    batch_job = genai_client.batches.create(model=model, src=src)
    name = batch_job.name
    if not name:
        raise RuntimeError("Batch job created but returned no name")
    logger.info("Created batch job %s", name)
    return name


@retry(
    retry=retry_if_exception_type(genai_errors.APIError),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=1, max=10, jitter=2),
)
def get_batch_job_status(
    genai_client: genai.Client,
    job_name: str,
) -> BatchJobResult:
    """Poll the Gemini API for the current state of *job_name*."""
    batch_job = genai_client.batches.get(name=job_name)
    if not batch_job.state:
        raise RuntimeError(f"Batch job {job_name} returned no state")
    state_name = batch_job.state.name

    if not BatchJobState.is_completed(state_name):
        logger.info("Batch job %s still running: %s", job_name, state_name)
        return BatchJobResult(job_name=job_name, state=state_name)

    if not BatchJobState.is_successful(state_name):
        msg = f"Batch job {job_name} ended with state {state_name}"
        logger.error(msg)
        return BatchJobResult(job_name=job_name, state=state_name, error=msg)

    if not batch_job.dest:
        msg = f"Batch job {job_name} succeeded but has no destination"
        logger.error(msg)
        return BatchJobResult(job_name=job_name, state=state_name, error=msg)

    file_name = batch_job.dest.file_name
    logger.info("Batch job %s succeeded, dest file=%s", job_name, file_name)
    return BatchJobResult(job_name=job_name, state=state_name, dest_file=file_name)


def parse_jsonl_results(
    content: bytes | str,
    line_parser: Callable[[dict[str, Any]], tuple[str | None, Any]],
) -> dict[str, Any]:
    """Decode JSONL bytes and apply *line_parser* to each line.

    *line_parser* should return ``(key, value)``; lines where ``key`` is
    ``None`` are silently skipped.
    """
    text = content.decode("utf-8") if isinstance(content, bytes) else content
    lines = [ln for ln in text.strip().split("\n") if ln.strip()]
    logger.info("Parsing %d result lines", len(lines))

    results: dict[str, Any] = {}
    for i, line in enumerate(lines):
        try:
            data = json.loads(line)
            key, value = line_parser(data)
            if key is not None:
                results[key] = value
        except json.JSONDecodeError:
            logger.error("Invalid JSON on line %d: %.100s", i, line)
        except Exception:
            logger.error("Error parsing line %d", i, exc_info=True)

    logger.info("Parsed %d results", len(results))
    return results
