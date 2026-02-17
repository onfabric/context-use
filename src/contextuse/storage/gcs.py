from __future__ import annotations

import io
from typing import BinaryIO

try:
    from google.cloud import storage as gcs_storage
except ImportError:
    gcs_storage = None  # type: ignore[assignment]

from contextuse.storage.base import StorageBackend


class GCSStorage(StorageBackend):
    """Google Cloud Storage backend.

    Requires ``google-cloud-storage``.  Install via::

        pip install "contextuse[gcs]"
    """

    def __init__(self, bucket: str, prefix: str = "", project: str | None = None) -> None:
        if gcs_storage is None:
            raise ImportError(
                "google-cloud-storage is required for GCSStorage. "
                "Install with: pip install 'contextuse[gcs]'"
            )
        self._client = gcs_storage.Client(project=project)
        self._bucket = self._client.bucket(bucket)
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""

    def _full_key(self, key: str) -> str:
        return f"{self._prefix}{key}"

    # ---- interface ----

    def write(self, key: str, data: bytes) -> None:
        blob = self._bucket.blob(self._full_key(key))
        blob.upload_from_string(data)

    def read(self, key: str) -> bytes:
        blob = self._bucket.blob(self._full_key(key))
        return blob.download_as_bytes()

    def open_stream(self, key: str) -> BinaryIO:
        data = self.read(key)
        return io.BytesIO(data)

    def list_keys(self, prefix: str) -> list[str]:
        full_prefix = self._full_key(prefix)
        blobs = self._client.list_blobs(self._bucket, prefix=full_prefix)
        # strip our root prefix so keys are relative
        strip = len(self._prefix)
        return sorted(blob.name[strip:] for blob in blobs)

    def exists(self, key: str) -> bool:
        blob = self._bucket.blob(self._full_key(key))
        return blob.exists()

    def delete(self, key: str) -> None:
        blob = self._bucket.blob(self._full_key(key))
        blob.delete()

