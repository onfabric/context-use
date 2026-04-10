from __future__ import annotations

import logging

from context_use.asset_description.extractor import (
    AssetDescriptionExtractor,
    DescriptionExtractor,
)
from context_use.asset_description.factory import AssetDescriptionBatchFactory
from context_use.asset_description.prompt import (
    AssetDescriptionPromptBuilder,
    AssetDescriptionSchema,
)
from context_use.asset_description.states import DescGenerateCompleteState
from context_use.batch.manager import (
    BaseBatchManager,
    BatchContext,
    register_batch_manager,
)
from context_use.batch.states import CompleteState, CreatedState, SkippedState, State
from context_use.llm.base import BatchResults
from context_use.models.batch import Batch, BatchCategory

logger = logging.getLogger(__name__)


@register_batch_manager(BatchCategory.asset_description)
class AssetDescriptionBatchManager(BaseBatchManager):
    """Generates AI descriptions for asset threads (images/videos).

    State machine:
        CREATED → DESC_GENERATE_PENDING → DESC_GENERATE_COMPLETE → COMPLETE
    """

    def __init__(self, batch: Batch, ctx: BatchContext) -> None:
        super().__init__(batch, ctx)
        self.extractor: DescriptionExtractor = AssetDescriptionExtractor(ctx.llm_client)
        self.batch_factory = AssetDescriptionBatchFactory

    async def _transition(self, current_state: State) -> State | None:
        match current_state:
            case CreatedState():
                logger.info("[%s] Starting asset description generation", self.batch.id)
                return await self._generate_descriptions()

            case DescGenerateCompleteState():
                logger.info("[%s] Asset description generation complete", self.batch.id)
                return CompleteState()

            case _:
                raise ValueError(
                    f"Invalid state for asset description batch: {current_state}"
                )

    async def _generate_descriptions(self) -> State:
        groups = await self.batch_factory.get_batch_groups(self.batch, self.ctx.store)
        threads = [t for g in groups for t in g.threads if t.asset_uri is not None]

        if not threads:
            return SkippedState(reason="No asset threads to generate descriptions for")

        builder = AssetDescriptionPromptBuilder(threads)
        prompts = builder.build()

        if not prompts:
            return SkippedState(reason="No prompts built from asset threads")

        logger.info(
            "[%s] Generating descriptions for %d asset threads",
            self.batch.id,
            len(prompts),
        )

        job_key = await self.extractor.submit(self.batch.id, prompts)
        results = await self.extractor.get_results(job_key)

        if results is None:
            return SkippedState(reason="Extractor returned no results")

        count = await self._store_descriptions(results)
        return DescGenerateCompleteState(descriptions_count=count)

    async def _store_descriptions(
        self, results: BatchResults[AssetDescriptionSchema]
    ) -> int:
        threads = await self.ctx.store.list_threads_by_ids(list(results.keys()))
        thread_map = {t.id: t for t in threads}

        count = 0
        for thread_id, schema in results.items():
            if not schema.description:
                continue
            thread = thread_map.get(thread_id)
            if thread is None:
                continue

            caption = thread.get_raw_content()
            if caption:
                composed = f"{schema.description}\n\n{caption}"
            else:
                composed = schema.description

            await self.ctx.store.update_thread_content(thread_id, composed)
            count += 1

        logger.info("[%s] Stored %d asset descriptions", self.batch.id, count)
        return count
