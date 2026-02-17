"""Abstract LLM interface for batch processing.

Mirrors the submit/poll pattern used by Gemini batch API, but is
provider-agnostic so we can swap in OpenAI / Anthropic later.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# Generic type alias — maps item_id → parsed result
BatchResults = dict[str, T]


@dataclass
class PromptItem:
    """A single prompt to send to the LLM.

    Equivalent to ``app.core.ai.schemas.PromptItem`` in aertex.

    Attributes:
        item_id:         Unique key for this item (thread_id, date string, etc.)
        prompt:          The text prompt.
        response_schema: JSON schema dict the LLM should conform to.
        asset_key:       Optional GCS / storage key for an image or video.
    """

    item_id: str
    prompt: str
    response_schema: dict
    asset_key: str | None = None


class BatchLLMClient(ABC):
    """Two-phase batch LLM: submit prompts, then poll for results.

    For synchronous providers that don't have a native batch API,
    the implementation can do all the work in ``submit`` and return
    a sentinel key, then return cached results from ``get_results``.
    """

    @abstractmethod
    def batch_submit(
        self,
        batch_id: str,
        prompts: list[PromptItem],
    ) -> str:
        """Submit a batch of prompts. Returns a ``job_key`` for polling."""

    @abstractmethod
    def batch_get_results(
        self,
        job_key: str,
        schema: type[T],
    ) -> BatchResults[T] | None:
        """Poll for results.

        Returns ``{item_id: parsed_model}`` when the job is done,
        or ``None`` if still processing.
        """
