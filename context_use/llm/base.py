from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from pydantic import BaseModel

type BatchResults[T: BaseModel] = dict[str, T]
type EmbedBatchResults = dict[str, list[float]]


@dataclass
class PromptItem:
    """A single prompt to send to the LLM.

    Attributes:
        item_id:         Unique key for this item (thread_id, date string, etc.)
        prompt:          The text prompt.
        response_schema: JSON schema dict the LLM should conform to.
        asset_uris:      URIs for images/videos to include as parts.
    """

    item_id: str
    prompt: str
    response_schema: dict
    asset_uris: list[str] = field(default_factory=list)


@dataclass
class EmbedItem:
    """A single text to embed.

    Attributes:
        item_id: Unique key (e.g. memory UUID).
        text:    The text to embed.
    """

    item_id: str
    text: str


class BaseLLMClient(ABC):
    """Provider-agnostic interface for LLM operations.

    Implementations must support two batch workflows (generation and
    embedding) each with a submit/poll pattern, plus single-shot
    completion, structured completion, and embedding.

    The submit methods return an opaque *job key*; the corresponding
    ``get_results`` method polls using that key and returns ``None``
    while the job is still running.
    """

    @abstractmethod
    async def batch_submit(self, batch_id: str, prompts: list[PromptItem]) -> str: ...

    @abstractmethod
    async def batch_get_results[T: BaseModel](
        self, job_key: str, schema: type[T]
    ) -> BatchResults | None: ...

    @abstractmethod
    async def embed_batch_submit(
        self, batch_id: str, items: list[EmbedItem]
    ) -> str: ...

    @abstractmethod
    async def embed_batch_get_results(
        self,
        job_key: str,
    ) -> EmbedBatchResults | None: ...

    @abstractmethod
    async def completion(self, prompt: str) -> str: ...

    @abstractmethod
    async def structured_completion[T: BaseModel](
        self,
        prompt: PromptItem,
        schema: type[T],
    ) -> T: ...

    @abstractmethod
    async def embed_query(self, text: str) -> list[float]: ...
