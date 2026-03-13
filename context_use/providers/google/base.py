from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Iterator
from typing import ClassVar, cast

import ijson
from pydantic import BaseModel

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import CURRENT_THREAD_PAYLOAD_VERSION, ThreadPayload
from context_use.models.etl_task import EtlTask
from context_use.providers.google.record import GoogleRecord
from context_use.providers.google.schemas import Model
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)

PROVIDER = "google"


class _BaseGooglePipe(Pipe[GoogleRecord]):
    provider = PROVIDER
    archive_version = 1
    record_schema = GoogleRecord
    file_schema: ClassVar[type[BaseModel]] = Model
    _recognised_prefixes: ClassVar[tuple[str, ...]] = ()

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[GoogleRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                self.file_schema.model_validate(raw)
                source_json = json.dumps(raw, default=str)
                record = cast(
                    GoogleRecord,
                    self.record_schema.model_validate(raw),
                )
                record.source = source_json
                if self._recognised_prefixes and not any(
                    record.title.startswith(p) for p in self._recognised_prefixes
                ):
                    continue
                yield record
        finally:
            stream.close()

    @staticmethod
    def clean_url(url: str | None) -> str | None:
        """Unwrap Google redirect URLs (``google.com/url?q=...``).

        Only unwraps when the path is ``/url`` — other Google URLs
        (``/search``, ``/maps/place/...``, ``local.google.com/place``)
        are returned as-is.
        """
        if not url:
            return None
        try:
            parsed = urllib.parse.urlparse(url)
            if (
                parsed.hostname
                and "google" in parsed.hostname
                and parsed.path == "/url"
            ):
                params = urllib.parse.parse_qs(parsed.query)
                q_values = params.get("q", [])
                if q_values and q_values[0]:
                    return q_values[0]
            return url
        except Exception:
            return url

    def transform(self, record: GoogleRecord, task: EtlTask) -> ThreadRow:
        payload = self._build_payload(record)
        assert payload is not None, (
            f"Unexpected None payload for title={record.title!r}; "
            "extract_file() should have filtered this record"
        )

        return ThreadRow(
            unique_key=payload.unique_key(),
            provider=self.provider,
            interaction_type=self.interaction_type,
            preview=payload.get_preview(task.provider) or "",
            payload=payload.to_dict(),
            version=CURRENT_THREAD_PAYLOAD_VERSION,
            asat=record.time,
            source=record.source,
        )

    def _build_payload(self, record: GoogleRecord) -> ThreadPayload:
        raise NotImplementedError
