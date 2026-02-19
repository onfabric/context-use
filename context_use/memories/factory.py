"""Batch factory for the memories pipeline."""

from __future__ import annotations

from context_use.batch.factory import BaseBatchFactory
from context_use.batch.models import BatchCategory


class MemoryBatchFactory(BaseBatchFactory):
    """Creates batches for the memories pipeline.

    No cutoff — all threads from the ETL task are eligible.
    """

    BATCH_CATEGORIES = [BatchCategory.memories]
    cutoff_days = None
