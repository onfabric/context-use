from __future__ import annotations

import logging

from context_use.asset_description.factory import AssetDescriptionBatchFactory
from context_use.asset_description.prompt import (
    AssetDescriptionPromptBuilder,
    AssetDescriptionSchema,
)
from context_use.asset_description.states import (
    DescGenerateCompleteState,
    DescGeneratePendingState,
)
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
    """Generates AI descriptions for image asset threads.

    State machine:
        CREATED → DESC_GENERATE_PENDING → DESC_GENERATE_COMPLETE → COMPLETE
    """

    def __init__(self, batch: Batch, ctx: BatchContext) -> None:
        super().__init__(batch, ctx)
        self.batch_factory = AssetDescriptionBatchFactory

    async def _transition(self, current_state: State) -> State | None:
        match current_state:
            case CreatedState():
                logger.info("[%s] Starting asset description generation", self.batch.id)
                return await self._submit_description_batch()

            case DescGeneratePendingState() as state:
                logger.info("[%s] Polling description generation status", self.batch.id)
                return await self._check_description_results(state)

            case DescGenerateCompleteState():
                logger.info("[%s] Asset description generation complete", self.batch.id)
                return CompleteState()

            case _:
                raise ValueError(
                    f"Invalid state for asset description batch: {current_state}"
                )

    async def _submit_description_batch(self) -> State:
        groups = await self.batch_factory.get_batch_groups(self.batch, self.ctx.store)
        threads = [t for g in groups for t in g.threads if t.asset_uri is not None]

        if not threads:
            return SkippedState(reason="No asset threads to generate descriptions for")

        builder = AssetDescriptionPromptBuilder(threads)
        prompts = builder.build()

        if not prompts:
            return SkippedState(reason="No prompts built from asset threads")

        logger.info(
            "[%s] Submitting batch job for %d asset threads",
            self.batch.id,
            len(prompts),
        )

        job_key = await self.ctx.llm_client.batch_submit(self.batch.id, prompts)
        return DescGeneratePendingState(job_key=job_key)

    async def _check_description_results(
        self, state: DescGeneratePendingState
    ) -> State:
        results = await self.ctx.llm_client.batch_get_results(
            state.job_key, AssetDescriptionSchema
        )
        if results is None:
            return state

        count = await self._store_descriptions(results)
        return DescGenerateCompleteState(descriptions_count=count)

    async def _store_descriptions(
        self, results: BatchResults[AssetDescriptionSchema]
    ) -> int:
        count = 0
        for thread_id, schema in results.items():
            if not schema.description:
                continue
            await self.ctx.store.update_thread_content(thread_id, schema.description)
            count += 1

        logger.info("[%s] Stored %d asset descriptions", self.batch.id, count)
        return count
