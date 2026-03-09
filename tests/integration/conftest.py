from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from pydantic import BaseModel

from context_use import ContextUse
from context_use.llm.base import (
    BaseLLMClient,
    BatchResults,
    EmbedBatchResults,
    EmbedItem,
    PromptItem,
)
from context_use.storage.disk import DiskStorage
from context_use.store.sqlite import SqliteStore


def pytest_collection_modifyitems(items: list, config) -> None:  # noqa: ANN001
    """Auto-mark every test in the integration directory."""
    marker = pytest.mark.integration
    for item in items:
        item.add_marker(marker)


class _StubLLMClient(BaseLLMClient):
    """Minimal stub for ETL-only integration tests that never call the LLM."""

    async def batch_submit(self, batch_id: str, prompts: list[PromptItem]) -> str:
        raise NotImplementedError

    async def batch_get_results[T: BaseModel](
        self, job_key: str, schema: type[T]
    ) -> BatchResults | None:
        raise NotImplementedError

    async def embed_batch_submit(self, batch_id: str, items: list[EmbedItem]) -> str:
        raise NotImplementedError

    async def embed_batch_get_results(self, job_key: str) -> EmbedBatchResults | None:
        raise NotImplementedError

    async def completion(self, prompt: str) -> str:
        raise NotImplementedError

    async def structured_completion[T: BaseModel](
        self, prompt: PromptItem, schema: type[T]
    ) -> T:
        raise NotImplementedError

    async def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


@pytest.fixture()
async def store(tmp_path: Path) -> AsyncGenerator[SqliteStore]:
    """Create a SqliteStore with a clean slate for each test."""
    s = SqliteStore(path=str(tmp_path / "integration_test.db"))
    await s.init()
    yield s
    await s.close()


@pytest.fixture()
def ctx(tmp_path: Path, store: SqliteStore) -> ContextUse:
    storage = DiskStorage(base_path=str(tmp_path / "storage"))
    return ContextUse(storage=storage, store=store, llm_client=_StubLLMClient())
