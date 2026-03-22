from __future__ import annotations

import io
from typing import BinaryIO

from context_use.storage.base import StorageBackend


class InMemoryStorage(StorageBackend):
    """In-memory storage backend, intended for use in tests."""

    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}

    def write(self, key: str, data: bytes) -> None:
        self._data[key] = data

    def read(self, key: str) -> bytes:
        return self._data[key]

    def open_stream(self, key: str) -> BinaryIO:
        return io.BytesIO(self._data[key])

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self._data if k.startswith(prefix))

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def resolve_uri(self, key: str) -> str:
        return key
