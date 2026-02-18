from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from context_use.storage.base import StorageBackend


class DiskStorage(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_path: str) -> None:
        self._base = Path(base_path)
        self._base.mkdir(parents=True, exist_ok=True)

    def _resolve(self, key: str) -> Path:
        return self._base / key

    # ---- interface ----

    def write(self, key: str, data: bytes) -> None:
        path = self._resolve(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, key: str) -> bytes:
        return self._resolve(key).read_bytes()

    def open_stream(self, key: str) -> BinaryIO:
        path = self._resolve(key)
        return open(path, "rb")  # noqa: SIM115

    def list_keys(self, prefix: str) -> list[str]:
        prefix_path = self._resolve(prefix)
        if not prefix_path.exists():
            return []
        if prefix_path.is_file():
            return [prefix]
        keys: list[str] = []
        for p in prefix_path.rglob("*"):
            if p.is_file():
                keys.append(str(p.relative_to(self._base)))
        return sorted(keys)

    def exists(self, key: str) -> bool:
        return self._resolve(key).exists()

    def delete(self, key: str) -> None:
        path = self._resolve(key)
        if path.is_file():
            path.unlink()
