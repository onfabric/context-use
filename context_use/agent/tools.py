from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import Field

from context_use.memories.service import MemoryService
from context_use.proxy.log import log_tool_action


def make_agent_tools(memory_service: MemoryService) -> list:

    async def list_memories(
        from_date: Annotated[
            str,
            Field(description="ISO date (YYYY-MM-DD). Start of the window to survey."),
        ],
        to_date: Annotated[
            str,
            Field(description="ISO date (YYYY-MM-DD). End of the window to survey."),
        ],
        limit: Annotated[
            int,
            Field(default=50, description="Maximum number of memories to return."),
        ] = 50,
    ) -> dict:
        """List active memories in date order within a specific time window.

        Use this to survey a well-defined date range.
        Always provide both from_date and to_date to bound the window.

        WARNING: results are capped at *limit* and may not include all memories
        in the requested range. If the window is large or you are unsure how many
        memories exist, use search_memories with a descriptive query instead.
        """
        rows = await memory_service.list_memories(
            from_date=date.fromisoformat(from_date),
            to_date=date.fromisoformat(to_date),
            limit=limit,
        )
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
        from_date: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "ISO date (YYYY-MM-DD). "
                    "Only return memories from this date onwards."
                ),
            ),
        ] = None,
        to_date: Annotated[
            str | None,
            Field(
                default=None,
                description=(
                    "ISO date (YYYY-MM-DD). Only return memories up to this date."
                ),
            ),
        ] = None,
        top_k: Annotated[
            int,
            Field(default=10, description="Maximum number of results to return."),
        ] = 10,
    ) -> dict:
        """Find memories semantically similar to a query, with optional date filters.

        Results are ranked by semantic similarity. Use from_date and to_date to further
        narrow the search to a specific time window.
        """
        parsed_from = date.fromisoformat(from_date) if from_date else None
        parsed_to = date.fromisoformat(to_date) if to_date else None
        results = await memory_service.search_memories(
            query=query,
            from_date=parsed_from,
            to_date=parsed_to,
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
        m = await memory_service.get_memory(memory_id)
        if m is None:
            return {"error": f"Memory {memory_id!r} not found"}
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
        from_dt = date.fromisoformat(from_date) if from_date else None
        to_dt = date.fromisoformat(to_date) if to_date else None
        try:
            await memory_service.update_memory(
                memory_id, content=content, from_date=from_dt, to_date=to_dt
            )
        except ValueError as exc:
            return {"error": str(exc)}
        log_tool_action("Updated", memory_id)
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
                    "IDs of the memories this was synthesised from. "
                    "Required for pattern memories and merges. "
                    "Pass every event memory used as evidence."
                ),
            ),
        ] = None,
    ) -> dict:
        """Write a new memory to the store.

        Call this to create a higher-level pattern memory distilled from multiple event
        memories. Pass all source event IDs in source_memory_ids for the audit trail.
        Do NOT archive the source memories when creating a pattern — they remain
        individually useful.
        """
        created = await memory_service.create_memory(
            content=content,
            from_date=date.fromisoformat(from_date),
            to_date=date.fromisoformat(to_date),
            source_memory_ids=source_memory_ids,
        )
        log_tool_action("Created", created.id)
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

        Use this after create_memory when merging duplicate event memories or
        splitting an over-broad memory, passing the new memory's ID as
        superseded_by.
        """
        archived = await memory_service.archive_memories(
            memory_ids, superseded_by=superseded_by
        )
        not_found = [mid for mid in memory_ids if mid not in set(archived)]

        log_tool_action("Archived", count=len(archived))
        result: dict = {"archived": archived}
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
