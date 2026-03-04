from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING, Annotated

from pydantic import Field

from context_use.models.memory import MemoryStatus, TapestryMemory
from context_use.models.utils import generate_uuidv4

if TYPE_CHECKING:
    from context_use.llm.base import BaseLLMClient
    from context_use.store.base import Store

logger = logging.getLogger(__name__)


def make_refinement_tools(store: Store, llm_client: BaseLLMClient) -> list:
    """Build the memory tool set for the refinement agent."""

    async def list_memories(
        from_date: Annotated[
            str | None,
            Field(
                default=None,
                description="ISO date (YYYY-MM-DD). Return memories from this date.",
            ),
        ] = None,
        to_date: Annotated[
            str | None,
            Field(
                default=None,
                description="ISO date (YYYY-MM-DD). Return memories before this date.",
            ),
        ] = None,
        limit: Annotated[
            int,
            Field(default=50, description="Maximum number of memories to return."),
        ] = 50,
    ) -> dict:
        """List active memories, optionally filtered by date range.

        Returns a list of memories with their IDs, content, and date spans.
        Use this to survey what exists before making any changes.
        """
        from_dt = date.fromisoformat(from_date) if from_date else None
        rows = await store.list_memories(
            status=MemoryStatus.active.value,
            from_date=from_dt,
            limit=limit,
        )
        if to_date:
            to_dt = date.fromisoformat(to_date)
            rows = [r for r in rows if r.to_date <= to_dt]
        return {
            "count": len(rows),
            "memories": [
                {
                    "id": m.id,
                    "content": m.content,
                    "from_date": m.from_date.isoformat(),
                    "to_date": m.to_date.isoformat(),
                }
                for m in rows
            ],
        }

    async def search_memories(
        query: Annotated[
            str,
            Field(description="Text query to find semantically similar memories."),
        ],
        top_k: Annotated[
            int,
            Field(default=10, description="Maximum number of results to return."),
        ] = 10,
    ) -> dict:
        """Find memories semantically similar to a text query.

        Use this to discover memories related to a specific topic or theme,
        which helps identify duplicates and closely related entries.
        """
        query_embedding = await llm_client.embed_query(query)
        results = await store.search_memories(
            query_embedding=query_embedding,
            top_k=top_k,
        )
        return {
            "count": len(results),
            "memories": [
                {
                    "id": r.id,
                    "content": r.content,
                    "from_date": r.from_date.isoformat(),
                    "to_date": r.to_date.isoformat(),
                    "similarity": round(r.similarity, 4)
                    if r.similarity is not None
                    else None,
                }
                for r in results
            ],
        }

    async def get_memory(
        memory_id: Annotated[
            str,
            Field(description="UUID of the memory to retrieve."),
        ],
    ) -> dict:
        """Retrieve the full details of a single memory by ID.

        Use this to read a memory's complete content before deciding
        whether to update, archive, or merge it.
        """
        memories = await store.get_memories([memory_id])
        if not memories:
            return {"error": f"Memory {memory_id!r} not found"}
        m = memories[0]
        return {
            "id": m.id,
            "content": m.content,
            "from_date": m.from_date.isoformat(),
            "to_date": m.to_date.isoformat(),
            "status": m.status,
            "source_memory_ids": m.source_memory_ids,
        }

    async def update_memory(
        memory_id: Annotated[
            str,
            Field(description="UUID of the memory to update."),
        ],
        content: Annotated[
            str | None,
            Field(default=None, description="New content. Omit to leave unchanged."),
        ] = None,
        from_date: Annotated[
            str | None,
            Field(
                default=None,
                description="New start date (YYYY-MM-DD). Omit to leave unchanged.",
            ),
        ] = None,
        to_date: Annotated[
            str | None,
            Field(
                default=None,
                description="New end date (YYYY-MM-DD). Omit to leave unchanged.",
            ),
        ] = None,
    ) -> dict:
        """Edit the content or date range of an existing memory.

        Use this for minor corrections such as rephrasing or fixing dates.
        For merges or splits, use create_memory + archive_memories instead.
        At least one of content, from_date, or to_date must be provided.
        """
        memories = await store.get_memories([memory_id])
        if not memories:
            return {"error": f"Memory {memory_id!r} not found"}
        m = memories[0]
        if content is not None:
            m.content = content
            embedding = await llm_client.embed_query(content)
            m.embedding = embedding
        if from_date is not None:
            m.from_date = date.fromisoformat(from_date)
        if to_date is not None:
            m.to_date = date.fromisoformat(to_date)
        await store.update_memory(m)
        logger.info("Updated memory %s", memory_id)
        return {"updated": memory_id}

    async def create_memory(
        content: Annotated[
            str,
            Field(description="Memory text, written in first-person narrative."),
        ],
        from_date: Annotated[
            str,
            Field(description="Start date in ISO format (YYYY-MM-DD)."),
        ],
        to_date: Annotated[
            str,
            Field(description="End date in ISO format (YYYY-MM-DD)."),
        ],
        source_memory_ids: Annotated[
            list[str] | None,
            Field(
                default=None,
                description=(
                    "IDs of the memories this was synthesised from "
                    "(required for merges and splits)."
                ),
            ),
        ] = None,
    ) -> dict:
        """Write a new memory to the store.

        Use this when merging two memories (create the combined result, then
        call archive_memories on the sources) or when splitting an over-broad
        memory into focused fragments (create each fragment, then archive the
        original). Always pass source_memory_ids so the audit trail is intact.
        """
        embedding = await llm_client.embed_query(content)
        memory = TapestryMemory(
            content=content,
            from_date=date.fromisoformat(from_date),
            to_date=date.fromisoformat(to_date),
            group_id=generate_uuidv4(),
            status=MemoryStatus.active.value,
            source_memory_ids=source_memory_ids,
            embedding=embedding,
        )
        created = await store.create_memory(memory)
        logger.info("Created memory %s (sources=%s)", created.id, source_memory_ids)
        return {"created_id": created.id}

    async def archive_memories(
        memory_ids: Annotated[
            list[str],
            Field(description="List of memory IDs to mark as superseded."),
        ],
        superseded_by: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "ID of the memory that replaces these. Pass the ID returned "
                    "by create_memory after a merge or split. Omit only when "
                    "archiving without a replacement."
                ),
            ),
        ] = None,
    ) -> dict:
        """Mark one or more memories as superseded.

        Always call this after create_memory when merging or splitting,
        passing the new memory's ID as superseded_by. This preserves
        the full audit trail without losing any historical content.
        """
        memories = await store.get_memories(memory_ids)
        found_ids = {m.id for m in memories}
        updated_ids: list[str] = []
        for m in memories:
            m.status = MemoryStatus.superseded.value
            if superseded_by:
                m.superseded_by = superseded_by
            await store.update_memory(m)
            updated_ids.append(m.id)
        not_found = [mid for mid in memory_ids if mid not in found_ids]
        logger.info(
            "Archived %d memories (superseded_by=%s)", len(updated_ids), superseded_by
        )
        result: dict = {"archived": updated_ids}
        if not_found:
            result["not_found"] = not_found
        return result

    return [
        list_memories,
        search_memories,
        get_memory,
        update_memory,
        create_memory,
        archive_memories,
    ]
