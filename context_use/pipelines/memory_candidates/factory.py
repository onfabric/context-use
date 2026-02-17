"""Batch factory for the memory-candidates pipeline."""

from __future__ import annotations

from context_use.batch.factory import BaseBatchFactory
from context_use.batch.models import BatchCategory


class MemoryCandidateBatchFactory(BaseBatchFactory):
    """Creates batches for the memory-candidates pipeline.

    No cutoff — all threads from the ETL task are eligible.
    """

    BATCH_CATEGORIES = [BatchCategory.memory_candidates]
    cutoff_days = None
