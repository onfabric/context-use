from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar

from pydantic import BaseModel

from context_use.etl.core.types import ThreadRow
from context_use.models.etl_task import EtlTask
from context_use.storage.base import StorageBackend


class Pipe[Record: BaseModel](ABC):
    """Base class for all interaction-type ETL pipes.

    A Pipe encapsulates the **Extract** and **Transform** steps for a
    single interaction type (e.g. ChatGPT conversations, Instagram
    stories).  Subclasses implement :meth:`extract_file` (parse one
    source file) and :meth:`transform` (shape each record into a
    :class:`ThreadRow`).

    The **Load** step is handled separately by the :class:`Store`.
    """

    provider: ClassVar[str]
    """Provider identifier (e.g. ``"chatgpt"``, ``"instagram"``)."""

    interaction_type: ClassVar[str]
    """Interaction type identifier (e.g. ``"chatgpt_conversations"``)."""

    archive_version: ClassVar[int]
    """Archive format version this pipe handles (e.g. ``1``).

    Bumps when the **provider's export format** changes (e.g. ChatGPT
    ships a new ``conversations.json`` structure).  Used for registry
    lookup, versioning-via-inheritance, and GCS path conventions.

    This is distinct from ``ThreadRow.version``, which tracks the
    *payload schema* version (``CURRENT_THREAD_PAYLOAD_VERSION``).
    """

    @classmethod
    def archive_version_label(cls) -> str:
        """Return ``'v{N}'`` string for GCS paths and display."""
        return f"v{cls.archive_version}"

    archive_path_pattern: ClassVar[str]
    """``fnmatch`` glob for the relative path inside the zip archive.

    Patterns without wildcards behave as exact matches (backward-compatible).
    Patterns with wildcards (e.g. ``inbox/*/message_1.json``) match multiple
    files; ``discover_tasks`` bundles **all matched files into one EtlTask**
    via ``task.source_uris``.  The base class :meth:`extract` loops over
    ``source_uris`` and calls :meth:`extract_file` for each, so subclasses
    always implement single-file logic.
    """

    record_schema: ClassVar[type[BaseModel]]
    """Runtime-accessible record type.  Must match the type parameter ``Record``.

    Python's generic type parameters are erased at runtime, so this
    ClassVar is needed for runtime introspection (e.g. registry
    validation, schema checks).  Subclasses should set this to the
    same model used as ``Record``.
    """

    @abstractmethod
    def extract_file(
        self, source_uri: str, storage: StorageBackend
    ) -> Iterator[Record]:
        """Parse one source file and yield validated records.

        Subclasses implement this for single-file logic.  The base
        class :meth:`extract` loops over ``task.source_uris`` and
        delegates to this method for each file.
        """
        ...

    def extract(self, task: EtlTask, storage: StorageBackend) -> Iterator[Record]:
        """Iterate over all source URIs, delegating to :meth:`extract_file`.

        Not intended to be overridden.  Subclasses implement
        :meth:`extract_file` for single-file logic.
        """
        for uri in task.source_uris:
            yield from self.extract_file(uri, storage)

    @abstractmethod
    def transform(self, record: Record, task: EtlTask) -> ThreadRow:
        """Convert one extracted record into a :class:`ThreadRow`."""
        ...

    def run(self, task: EtlTask, storage: StorageBackend) -> Iterator[ThreadRow]:
        """Run the extract → transform loop.

        Yields :class:`ThreadRow` instances one at a time, keeping memory
        bounded.  Not intended to be overridden.

        After the iterator is fully consumed, :attr:`extracted_count` and
        :attr:`transformed_count` reflect the totals.
        """
        self.extracted_count: int = 0
        self.transformed_count: int = 0
        for record in self.extract(task, storage):
            self.extracted_count += 1
            row = self.transform(record, task)
            # Today transform() always returns a ThreadRow, but when it
            # evolves to -> ThreadRow | None (Phase A5), this guard is ready.
            if row is not None:
                self.transformed_count += 1
                yield row
