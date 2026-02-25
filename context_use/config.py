from __future__ import annotations

from typing import TYPE_CHECKING, Any

from context_use.storage.base import StorageBackend
from context_use.store.base import Store

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient


class _Registry[T]:
    """Lazily-populated factory registry.

    Each backend module registers itself via :meth:`register`.
    :meth:`build` resolves a provider name to a factory, calling
    ``factory.from_config(config)`` if available, otherwise
    ``factory(**config)``.
    """

    def __init__(self, label: str) -> None:
        self._label = label
        self._factories: dict[str, type[T]] = {}
        self._defaults_loaded = False

    def register(self, name: str, cls: type[T]) -> None:
        self._factories[name] = cls

    def build(self, provider: str, config: dict[str, Any]) -> T:
        if not self._defaults_loaded:
            self._load_defaults()
            self._defaults_loaded = True

        factory = self._factories.get(provider)
        if factory is None:
            raise ValueError(
                f"Unknown {self._label} provider '{provider}'. "
                f"Available: {list(self._factories)}"
            )
        if hasattr(factory, "from_config"):
            return factory.from_config(config)  # type: ignore[return-value]
        return factory(**config)  # type: ignore[return-value]

    def _load_defaults(self) -> None:
        """Override point — subclasses populate built-in factories here."""


class _StorageRegistry(_Registry[StorageBackend]):
    def _load_defaults(self) -> None:
        from context_use.storage.disk import DiskStorage

        self.register("disk", DiskStorage)

        try:
            from context_use.storage.gcs import GCSStorage

            self.register("gcs", GCSStorage)
        except ImportError:
            pass


class _StoreRegistry(_Registry[Store]):
    def _load_defaults(self) -> None:
        from context_use.store.memory import InMemoryStore

        self.register("memory", InMemoryStore)

        try:
            from context_use.store.postgres import PostgresStore

            self.register("postgres", PostgresStore)
        except ImportError:
            pass


class _LLMRegistry(_Registry["BaseLLMClient"]):
    def _load_defaults(self) -> None:
        from context_use.llm.litellm import LiteLLMBatchClient, LiteLLMSyncClient

        self.register("openai", LiteLLMBatchClient)
        self.register("openai-sync", LiteLLMSyncClient)

    def build(self, provider: str, config: dict[str, Any]) -> BaseLLMClient:
        if provider == "openai" and config.get("mode") == "sync":
            provider = "openai-sync"
        return super().build(provider, config)


# Singleton instances
storage_registry = _StorageRegistry("storage")
store_registry = _StoreRegistry("store")
llm_registry = _LLMRegistry("llm")


def parse_config(
    config: dict[str, Any],
) -> tuple[StorageBackend, Store, BaseLLMClient]:
    """Parse a user config dict and return (storage, store, llm_client).

    Expected shape::

        {
            "storage": {"provider": "disk", "config": {"base_path": "/tmp"}},
            "store": {"provider": "memory", "config": {}},
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

    storage = storage_registry.build(
        storage_cfg.get("provider", "disk"),
        storage_cfg.get("config", {}),
    )
    store = store_registry.build(
        store_cfg.get("provider", "memory"),
        store_cfg.get("config", {}),
    )
    llm_client = llm_registry.build(
        llm_cfg.get("provider", "openai"),
        llm_cfg,
    )

    return storage, store, llm_client
