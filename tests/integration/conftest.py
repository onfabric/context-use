from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from context_use import ContextUse
from context_use.llm.litellm.clients import LiteLLMSyncClient
from context_use.llm.litellm.config import OpenAIConfig
from context_use.llm.litellm.models import OpenAIEmbeddingModel, OpenAIModel
from context_use.storage.disk import DiskStorage
from context_use.store.sqlite import SqliteStore

_STUB_CONFIG = OpenAIConfig(
    model=OpenAIModel.GPT_5_2,
    embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    api_key="stub",
)


@pytest.fixture()
async def store(tmp_path: Path) -> AsyncGenerator[SqliteStore]:
    s = SqliteStore(path=str(tmp_path / "integration_test.db"))
    await s.init()
    yield s
    await s.close()


@pytest.fixture()
def ctx(tmp_path: Path, store: SqliteStore) -> ContextUse:
    storage = DiskStorage(base_path=str(tmp_path / "storage"))
    return ContextUse(
        storage=storage, store=store, llm_client=LiteLLMSyncClient(_STUB_CONFIG)
    )
