from __future__ import annotations

from typing import ClassVar

from context_use.batch.factory import BaseBatchFactory
from context_use.models.batch import BatchCategory


class AssetDescriptionBatchFactory(BaseBatchFactory):
    BATCH_CATEGORIES: ClassVar[list[BatchCategory]] = [BatchCategory.asset_description]
    MAX_GROUPS_PER_BATCH = 25
