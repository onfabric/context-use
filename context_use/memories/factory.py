from __future__ import annotations

from context_use.batch.factory import BaseBatchFactory
from context_use.models.batch import BatchCategory


class MemoryBatchFactory(BaseBatchFactory):
    """Creates batches for the memories pipeline."""

    BATCH_CATEGORIES = [BatchCategory.memories]
