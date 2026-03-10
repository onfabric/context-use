
from collections.abc import Iterator

from context_use.etl.payload.models import (
    FibreSearch,
    Page,
    ThreadPayload,
)
from context_use.providers.google.base import _BaseGooglePipe
from context_use.providers.google.schemas import GoogleRecord
from context_use.providers.registry import declare_interaction
from context_use.providers.types import InteractionConfig
from context_use.storage.base import StorageBackend

_LENS_PLUS_PREFIX = "Searched with Google Lens + "
_SEARCHED_FOR_PREFIX = "Searched for "

# Order matters: check longer prefixes first so that
# ``"Searched with Google Lens + ..."`` is not confused with the bare
# ``"Searched with Google Lens"`` camera-only record.
_RECOGNISED_PREFIXES = (_LENS_PLUS_PREFIX, _SEARCHED_FOR_PREFIX)


class GoogleLensPipe(_BaseGooglePipe):
    """Google Lens activity.

    Handles three title patterns:

    - ``"Searched with Google Lens + \\"<query>\\""`` — visual search with
      text refinement → :class:`FibreSearch`
    - ``"Searched for <query>"`` — text search after a Lens session
      → :class:`FibreSearch`
    - ``"Searched with Google Lens"`` (bare) — camera-only, no textual
      content → filtered out during extraction (consistent with aertex).
    """

    interaction_type = "google_lens"
    archive_path_pattern = "Portability/My Activity/Google Lens/MyActivity.json"

    def extract_file(
        self,
        source_uri: str,
        storage: StorageBackend,
    ) -> Iterator[GoogleRecord]:
        for record in super().extract_file(source_uri, storage):
            if any(record.title.startswith(p) for p in _RECOGNISED_PREFIXES):
                yield record

    def _build_payload(self, record: GoogleRecord) -> ThreadPayload:
        url = self.clean_url(record.titleUrl)
        published = record.time

        # "Searched with Google Lens + "query"" → extract the quoted query
        if record.title.startswith(_LENS_PLUS_PREFIX):
            name = record.title[len(_LENS_PLUS_PREFIX) :].strip().strip('"') or None
            page = Page(name=name, url=url, published=published)  # type: ignore[reportCallIssue]
            return FibreSearch(object=page, published=published)  # type: ignore[reportCallIssue]

        # "Searched for <query>"
        if record.title.startswith(_SEARCHED_FOR_PREFIX):
            name = record.title[len(_SEARCHED_FOR_PREFIX) :].strip() or None
            page = Page(name=name, url=url, published=published)  # type: ignore[reportCallIssue]
            return FibreSearch(object=page, published=published)  # type: ignore[reportCallIssue]

        raise ValueError(f"Unrecognised Lens title prefix: {record.title!r}")


declare_interaction(InteractionConfig(pipe=GoogleLensPipe, memory=None))
