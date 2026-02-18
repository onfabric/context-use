from typing import Any

from context_use.db.base import DatabaseBackend
from context_use.storage.base import StorageBackend


_STORAGE_FACTORIES: dict[str, type] = {}
_DB_FACTORIES: dict[str, type] = {}


def _register_storage_defaults() -> None:
    if _STORAGE_FACTORIES:
        return
    from context_use.storage.disk import DiskStorage

    _STORAGE_FACTORIES["disk"] = DiskStorage


def _register_db_defaults() -> None:
    if _DB_FACTORIES:
        return
    from context_use.db.sqlite import SQLiteBackend

    _DB_FACTORIES["sqlite"] = SQLiteBackend


def build_storage(provider: str, config: dict[str, Any]) -> StorageBackend:
    _register_storage_defaults()
    cls = _STORAGE_FACTORIES.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown storage provider '{provider}'. "
            f"Available: {list(_STORAGE_FACTORIES.keys())}"
        )
    return cls(**config)


def build_db(provider: str, config: dict[str, Any]) -> DatabaseBackend:
    _register_db_defaults()
    cls = _DB_FACTORIES.get(provider)
    if cls is None:
        raise ValueError(
            f"Unknown db provider '{provider}'. "
            f"Available: {list(_DB_FACTORIES.keys())}"
        )
    return cls(**config)


def parse_config(
    config: dict[str, Any],
) -> tuple[StorageBackend, DatabaseBackend]:
    storage_cfg = config.get("storage", {})
    db_cfg = config.get("db", {})

    storage = build_storage(
        storage_cfg.get("provider", "disk"),
        storage_cfg.get("config", {}),
    )
    db = build_db(
        db_cfg.get("provider", "sqlite"),
        db_cfg.get("config", {}),
    )

    return storage, db

