from __future__ import annotations

from typing import TYPE_CHECKING, Any

from context_use.storage.base import StorageBackend
from context_use.store.base import Store

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient

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


_LLM_FACTORIES: dict[str, type] = {}


def _register_llm_defaults() -> None:
    """Lazily register built-in LLM backends."""
    if _LLM_FACTORIES:
        return

    from context_use.llm.litellm import LiteLLMBatchClient, LiteLLMSyncClient

    _LLM_FACTORIES["openai"] = LiteLLMBatchClient
    _LLM_FACTORIES["openai-sync"] = LiteLLMSyncClient


def build_llm(config: dict[str, Any]):
    """Build a BaseLLMClient from a config dict.

    Expected shape for OpenAI (default)::

        {"provider": "openai", "api_key": "sk-...",
         "model": "gpt-4o", "embedding_model": "text-embedding-3-large",
         "mode": "batch"}

    The ``provider`` key selects the backend; defaults to ``"openai"``.
    For OpenAI, ``mode`` can be ``"sync"`` (real-time completions) or
    ``"batch"`` (default, uses the OpenAI batch API).

    Additional backends (e.g. Gemini) can be registered at import time
    or by calling ``_LLM_FACTORIES["gemini"] = GeminiBatchClient``.
    """
    from context_use.llm.base import BaseLLMClient

    _register_llm_defaults()

    provider = config.get("provider", "openai")

    # OpenAI shorthand: "mode": "sync" maps to the "openai-sync" factory.
    if provider == "openai" and config.get("mode") == "sync":
        provider = "openai-sync"

    factory = _LLM_FACTORIES.get(provider)
    if factory is None:
        raise ValueError(
            f"Unknown LLM provider '{provider}'. "
            f"Available: {list(_LLM_FACTORIES.keys())}"
        )

    client = _build_llm_from_factory(provider, factory, config)
    if not isinstance(client, BaseLLMClient):
        raise TypeError(
            f"LLM factory for '{provider}' returned {type(client).__name__}, "
            f"expected BaseLLMClient"
        )
    return client


def _build_llm_from_factory(
    provider: str,
    factory: type,
    config: dict[str, Any],
):
    """Dispatch to the right constructor based on provider."""
    if provider in ("openai", "openai-sync"):
        return _build_openai_llm(factory, config)
    return factory(**config)


def _build_openai_llm(factory: type, config: dict[str, Any]):
    """Construct an OpenAI-backed LLM client from config."""
    from context_use.llm.models import OpenAIEmbeddingModel, OpenAIModel

    api_key = config.get("api_key", "")
    model = OpenAIModel(config.get("model", OpenAIModel.GPT_4O.value))
    embedding_model = OpenAIEmbeddingModel(
        config.get("embedding_model", OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE.value)
    )
    return factory(model=model, api_key=api_key, embedding_model=embedding_model)


def parse_config(
    config: dict[str, Any],
) -> tuple[StorageBackend, Store, BaseLLMClient]:
    """Parse a user config dict and return (storage, store, llm_client).

    Expected shape::

        {
            "storage": {"provider": "disk", "config": {"base_path": "/tmp"}},
            "store": {
              "provider": "memory",
              "config": {},
            },
            "llm": {"api_key": "sk-..."},
        }

    If no ``store`` key is present, defaults to in-memory.
    The legacy ``db`` key is accepted as an alias for ``store``.
    The ``llm`` section is required.
    """
    storage_cfg = config.get("storage", {})
    store_cfg = config.get("store") or config.get("db", {})
    llm_cfg = config.get("llm")
    if not llm_cfg:
        raise ValueError(
            "Missing 'llm' config section. "
            'Provide at least {"llm": {"api_key": "sk-..."}}.'
        )

    storage = build_storage(
        storage_cfg.get("provider", "disk"),
        storage_cfg.get("config", {}),
    )
    store = build_store(
        store_cfg.get("provider", "memory"),
        store_cfg.get("config", {}),
    )
    llm_client = build_llm(llm_cfg)

    return storage, store, llm_client
