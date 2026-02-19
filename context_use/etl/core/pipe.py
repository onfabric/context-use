from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from typing import ClassVar

from pydantic import BaseModel

from context_use.etl.core.types import ThreadRow
from context_use.etl.models.etl_task import EtlTask
from context_use.storage.base import StorageBackend


class Pipe[R: BaseModel](ABC):
    """Base class for all interaction-type ETL pipes.

    A Pipe encapsulates the **Extract** and **Transform** steps for a
    single interaction type (e.g. ChatGPT conversations, Instagram
    stories).  Subclasses implement :meth:`extract` (parse the archive)
    and :meth:`transform` (shape each record into a :class:`ThreadRow`).

    The **Load** step is handled separately by a :class:`Loader`.
    """

    provider: ClassVar[str]
    """Provider identifier (e.g. ``"chatgpt"``, ``"instagram"``)."""

    interaction_type: ClassVar[str]
    """Interaction type identifier (e.g. ``"chatgpt_conversations"``)."""

    archive_version: ClassVar[str]
    """Archive format version this pipe handles (e.g. ``"v1"``).

    Bumps when the **provider's export format** changes (e.g. ChatGPT
    ships a new ``conversations.json`` structure).  Used for registry
    lookup, versioning-via-inheritance, and GCS path conventions.

    This is distinct from ``ThreadRow.version``, which tracks the
    *payload schema* version (``CURRENT_THREAD_PAYLOAD_VERSION``).
    """

    archive_path: ClassVar[str]
    """Relative file path inside the zip archive this pipe reads from."""

    record_schema: ClassVar[type[BaseModel]]
    """Runtime-accessible record type.  Must match the type parameter ``R``.

    Python's generic type parameters are erased at runtime, so this
    ClassVar is needed for runtime introspection (e.g. registry
    validation, schema checks).  Subclasses should set this to the
    same model used as ``R``.
    """

    @abstractmethod
    def extract(self, task: EtlTask, storage: StorageBackend) -> Iterator[R]:
        """Parse raw archive data and yield validated records."""
        ...

    @abstractmethod
    def transform(self, record: R, task: EtlTask) -> ThreadRow:
        """Convert one extracted record into a :class:`ThreadRow`."""
        ...

    def run(self, task: EtlTask, storage: StorageBackend) -> Iterator[ThreadRow]:
        """Run the extract → transform loop.

        Yields :class:`ThreadRow` instances one at a time, keeping memory
        bounded.  Not intended to be overridden.
        """
        for record in self.extract(task, storage):
            yield self.transform(record, task)
