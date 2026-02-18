"""Configuration validation and backend factory."""

from __future__ import annotations

from typing import Any

from context_use.db.base import DatabaseBackend
from context_use.storage.base import StorageBackend

# ---------------------------------------------------------------------------
# Storage factories
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# DB factories
# ---------------------------------------------------------------------------

_DB_FACTORIES: dict[str, type] = {}


def _register_db_defaults() -> None:
    if _DB_FACTORIES:
        return

    try:
        from context_use.db.postgres import PostgresBackend

        _DB_FACTORIES["postgres"] = PostgresBackend
    except ImportError:
        pass


def build_db(provider: str, config: dict[str, Any]) -> DatabaseBackend:
    _register_db_defaults()
    cls = _DB_FACTORIES.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown db provider '{provider}'. Available: {list(_DB_FACTORIES.keys())}"
        )
    return cls(**config)


# ---------------------------------------------------------------------------
# Top-level config dict → backends
# ---------------------------------------------------------------------------


def parse_config(
    config: dict[str, Any],
) -> tuple[StorageBackend, DatabaseBackend]:
    """Parse a user config dict and return (storage, db) backends.

    Expected shape::

        {
            "storage": {"provider": "disk", "config": {"base_path": "/tmp"}},
            "db": {
              "provider": "postgres",
              "config": {
                "host": "localhost",
                "port": 5432,
                "database": "context_use",
                "user": "postgres",
                "password": "postgres",
              },
            },
        }
    """
    storage_cfg = config.get("storage", {})
    db_cfg = config.get("db", {})

    storage = build_storage(
        storage_cfg.get("provider", "disk"),
        storage_cfg.get("config", {}),
    )
    db = build_db(
        db_cfg.get("provider", "postgres"),
        db_cfg.get("config", {}),
    )

    return storage, db
