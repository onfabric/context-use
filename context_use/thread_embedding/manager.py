from __future__ import annotations

import logging

from context_use.batch.manager import (
    BaseBatchManager,
    BatchContext,
    register_batch_manager,
)
from context_use.batch.states import CompleteState, CreatedState, SkippedState, State
from context_use.models.batch import Batch, BatchCategory
from context_use.thread_embedding.embedding import (
    store_thread_embeddings,
    submit_thread_embeddings,
)
from context_use.thread_embedding.factory import ThreadEmbeddingBatchFactory
from context_use.thread_embedding.states import (
    ThreadEmbedCompleteState,
    ThreadEmbedPendingState,
)

logger = logging.getLogger(__name__)


@register_batch_manager(BatchCategory.thread_embedding)
class ThreadEmbeddingBatchManager(BaseBatchManager):
    """Embeds thread content for semantic search.

    State machine:
        CREATED → THREAD_EMBED_PENDING → THREAD_EMBED_COMPLETE → COMPLETE
    """

    def __init__(self, batch: Batch, ctx: BatchContext) -> None:
        super().__init__(batch, ctx)
        self.batch_factory = ThreadEmbeddingBatchFactory

    async def _transition(self, current_state: State) -> State | None:
        match current_state:
            case CreatedState():
                return await self._submit_embeddings()
            case ThreadEmbedPendingState() as state:
                return await self._check_embedding_status(state)
            case ThreadEmbedCompleteState():
                return CompleteState()
            case _:
                raise ValueError(
                    f"Invalid state for thread embedding batch: {current_state}"
                )

    async def _submit_embeddings(self) -> State:
        groups = await self.batch_factory.get_batch_groups(self.batch, self.ctx.store)
        threads = [t for g in groups for t in g.threads]

        embeddable = [t for t in threads if t.get_embeddable_content() is not None]
        if not embeddable:
            return SkippedState(reason="No threads with embeddable content")

        logger.info(
            "[%s] Submitting embed batch for %d threads",
            self.batch.id,
            len(embeddable),
        )
        job_key = await submit_thread_embeddings(
            embeddable, self.batch.id, self.ctx.llm_client
        )
        return ThreadEmbedPendingState(job_key=job_key)

    async def _check_embedding_status(self, state: ThreadEmbedPendingState) -> State:
        results = await self.ctx.llm_client.embed_batch_get_results(state.job_key)
        if results is None:
            return state

        count = await store_thread_embeddings(results, self.batch.id, self.ctx.store)
        return ThreadEmbedCompleteState(embedded_count=count)
