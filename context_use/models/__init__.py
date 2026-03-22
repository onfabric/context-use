"""Domain models — pure Python dataclasses with no infrastructure dependencies.

These models represent the core business entities of context_use.
They are the canonical types used by the Store protocol and all
non-persistence code (groupers, prompt builders, pipes, etc.).
"""

from context_use.models.archive import Archive, ArchiveStatus
from context_use.models.batch import Batch, BatchCategory, BatchThread
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.models.facet import Facet, MemoryFacet
from context_use.models.memory import MemoryStatus, TapestryMemory
from context_use.models.thread import NonEmptyThreads, Thread
from context_use.models.utils import generate_uuidv4

__all__ = [
    "generate_uuidv4",
    "Archive",
    "ArchiveStatus",
    "Batch",
    "BatchCategory",
    "BatchThread",
    "EtlTask",
    "EtlTaskStatus",
    "Facet",
    "MemoryFacet",
    "MemoryStatus",
    "TapestryMemory",
    "NonEmptyThreads",
    "Thread",
]
