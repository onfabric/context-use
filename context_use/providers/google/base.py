from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Iterator

import ijson

from context_use.etl.core.pipe import Pipe
from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import CURRENT_THREAD_PAYLOAD_VERSION, ThreadPayload
from context_use.models.etl_task import EtlTask
from context_use.providers.google.schemas import PROVIDER, GoogleRecord
from context_use.storage.base import StorageBackend

logger = logging.getLogger(__name__)


class _BaseGooglePipe(Pipe[GoogleRecord]):
    """Shared infrastructure for all Google Takeout pipes.

    Handles ``ijson`` streaming in :meth:`extract_file`, URL cleanup,
    and a shared :meth:`transform` that delegates payload construction
    to :meth:`_build_payload`.

    Subclasses set ``interaction_type``, ``archive_path_pattern``, and
    implement :meth:`_build_payload`.
    """

    provider = PROVIDER
    archive_version = 1
    record_schema = GoogleRecord

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[GoogleRecord]:
        stream = storage.open_stream(source_uri)
        try:
            for raw in ijson.items(stream, "item"):
                source_json = json.dumps(raw, default=str)
                try:
                    record = GoogleRecord.model_validate(raw)
                except Exception:
                    logger.debug(
                        "%s: skipping invalid record in %s",
                        self.__class__.__name__,
                        source_uri,
                    )
                    continue
                record.source = source_json
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
        """Build an ActivityStreams payload from a Google record.

        Subclasses must override this.  It is guaranteed to be called
        only for records that survived prefix filtering in
        :meth:`extract_file`.
        """
        raise NotImplementedError
