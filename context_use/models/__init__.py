"""Domain models — pure Python dataclasses with no infrastructure dependencies.

These models represent the core business entities of context_use.
They are the canonical types used by the Store protocol and all
non-persistence code (groupers, prompt builders, pipes, etc.).

The SQLAlchemy ORM models (used by PostgresStore) live separately
in ``etl/models/``, ``memories/models.py``, ``batch/models.py``,
and ``profile/models.py``.  They map to/from these domain models.
"""

from context_use.models.archive import Archive, ArchiveStatus
from context_use.models.batch import Batch, BatchCategory, BatchThread
from context_use.models.etl_task import EtlTask, EtlTaskStatus
from context_use.models.memory import EMBEDDING_DIMENSIONS, MemoryStatus, TapestryMemory
from context_use.models.profile import TapestryProfile
from context_use.models.thread import Thread

__all__ = [
    "Archive",
    "ArchiveStatus",
    "Batch",
    "BatchCategory",
    "BatchThread",
    "EMBEDDING_DIMENSIONS",
    "EtlTask",
    "EtlTaskStatus",
    "MemoryStatus",
    "TapestryMemory",
    "TapestryProfile",
    "Thread",
]
