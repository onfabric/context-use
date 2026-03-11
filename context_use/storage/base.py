from __future__ import annotations

from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageBackend(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def write(self, key: str, data: bytes) -> None:
        """Write data to the given key."""
        ...

    @abstractmethod
    def read(self, key: str) -> bytes:
        """Read data from the given key."""
        ...

    @abstractmethod
    def open_stream(self, key: str) -> BinaryIO:
        """Open a binary stream for the given key (for large files / streaming)."""
        ...

    @abstractmethod
    def list_keys(self, prefix: str) -> list[str]:
        """List all keys with the given prefix."""
        ...

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if the key exists."""
        ...

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete the given key."""
        ...

    @abstractmethod
    def resolve_uri(self, key: str) -> str:
        """Return a URI suitable for external consumption."""
        ...
