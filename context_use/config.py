from __future__ import annotations

from typing import Any

from context_use.storage.base import StorageBackend
from context_use.store.base import Store

_STORAGE_FACTORIES: dict[str, type] = {}


def _register_storage_defaults() -> None:
    """Lazily register built-in storage backends."""
    if _STORAGE_FACTORIES:
        return

    from context_use.storage.disk import DiskStorage

    _STORAGE_FACTORIES["disk"] = DiskStorage

    try:
        from context_use.storage.gcs import GCSStorage

        _STORAGE_FACTORIES["gcs"] = GCSStorage
    except ImportError:
        pass


def build_storage(provider: str, config: dict[str, Any]) -> StorageBackend:
    _register_storage_defaults()
    cls = _STORAGE_FACTORIES.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown storage provider '{provider}'. "
            f"Available: {list(_STORAGE_FACTORIES.keys())}"
        )
    return cls(**config)


_STORE_FACTORIES: dict[str, type] = {}


def _register_store_defaults() -> None:
    if _STORE_FACTORIES:
        return

    from context_use.store.memory import InMemoryStore

    _STORE_FACTORIES["memory"] = InMemoryStore

    try:
        from context_use.store.postgres import PostgresStore

        _STORE_FACTORIES["postgres"] = PostgresStore
    except ImportError:
        pass


def build_store(provider: str, config: dict[str, Any]) -> Store:
    _register_store_defaults()
    cls = _STORE_FACTORIES.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown store provider '{provider}'. "
            f"Available: {list(_STORE_FACTORIES.keys())}"
        )
    return cls(**config)


def build_llm(config: dict[str, Any]):
    """Build a BaseLLMClient from a config dict.

    Expected shape::

        {"api_key": "sk-...", "model": "gpt-4o",
         "embedding_model": "text-embedding-3-large",
         "mode": "batch"}

    Only ``api_key`` is required; the rest have sensible defaults.

    Set ``mode`` to ``"sync"`` for real-time completions (quickstart),
    or ``"batch"`` (default) for the OpenAI batch API.
    """
    from context_use.llm import (
        LiteLLMBatchClient,
        LiteLLMSyncClient,
        OpenAIEmbeddingModel,
        OpenAIModel,
    )

    api_key = config.get("api_key", "")
    model = OpenAIModel(config.get("model", OpenAIModel.GPT_4O.value))
    embedding_model = OpenAIEmbeddingModel(
        config.get("embedding_model", OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE.value)
    )
    mode = config.get("mode", "batch")

    cls = LiteLLMSyncClient if mode == "sync" else LiteLLMBatchClient
    return cls(model=model, api_key=api_key, embedding_model=embedding_model)


def parse_config(
    config: dict[str, Any],
) -> tuple[StorageBackend, Store]:
    """Parse a user config dict and return (storage, store) backends.

    Expected shape::

        {
            "storage": {"provider": "disk", "config": {"base_path": "/tmp"}},
            "store": {
              "provider": "memory",
              "config": {},
            },
        }

    If no ``store`` key is present, defaults to in-memory.
    The legacy ``db`` key is accepted as an alias for ``store``.
    """
    storage_cfg = config.get("storage", {})
    store_cfg = config.get("store") or config.get("db", {})

    storage = build_storage(
        storage_cfg.get("provider", "disk"),
        storage_cfg.get("config", {}),
    )
    store = build_store(
        store_cfg.get("provider", "memory"),
        store_cfg.get("config", {}),
    )

    return storage, store
