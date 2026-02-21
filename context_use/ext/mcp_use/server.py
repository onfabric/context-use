# pyright: reportMissingImports=false, reportCallIssue=false, reportGeneralTypeIssues=false
"""MCP server factory for context_use (requires the ``mcp-use`` extra).

Usage::

    from context_use import ContextUse
    from context_use.ext.mcp_use.server import create_server

    ctx = ContextUse.from_config({...})
    server = create_server(ctx)
    server.run(transport="streamable-http")
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp_use.server import MCPServer

    from context_use import ContextUse


def create_server(
    ctx: ContextUse,
    *,
    name: str = "context-use",
    version: str = "0.1.0",
) -> MCPServer:
    """Build an MCPServer with search and profile tools registered.

    Requires the ``mcp-use`` extra (``pip install context-use[mcp-use]``).

    Args:
        ctx: A fully configured :class:`ContextUse` instance.
        name: Server name exposed to MCP clients.
        version: Server version exposed to MCP clients.
    """
    try:
        from mcp.types import ToolAnnotations
        from mcp_use.server import MCPServer as _MCPServer
    except ImportError:
        raise ImportError(
            "mcp-use is required for MCP server support. "
            "Install it with: pip install context-use[mcp-use]"
        ) from None

    server = _MCPServer(
        name=name,
        version=version,
        instructions=(
            "Context server. Use get_profile to load the user's profile "
            "at the start of a conversation, and search_memories to recall "
            "specific episodes."
        ),
    )

    @server.tool(
        title="Get User Profile",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    async def get_profile() -> dict:
        """Get the user's profile — a structured summary of who they are.

        Returns a markdown profile distilled from the user's memories.
        Call this at the start of a conversation to understand who the
        user is. Use ``search_memories`` for specific episode recall.
        """
        profile = await ctx.get_profile()
        if profile is None:
            return {"content": None, "generated_at": None}
        return {
            "content": profile.content,
            "generated_at": profile.generated_at.isoformat(),
            "memory_count": profile.memory_count,
        }

    @server.tool(
        title="Search Memories",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
    )
    async def search(
        query: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        top_k: int = 5,
    ) -> list[dict]:
        """Search user memories by semantic similarity, date range, or both.

        Provide at least one of ``query``, ``from_date``, or ``to_date``.
        Dates should be ISO-8601 format (YYYY-MM-DD).
        """
        parsed_from = date.fromisoformat(from_date) if from_date else None
        parsed_to = date.fromisoformat(to_date) if to_date else None

        results = await ctx.search_memories(
            query=query,
            from_date=parsed_from,
            to_date=parsed_to,
            top_k=top_k,
        )

        out = []
        for r in results:
            entry: dict = {
                "id": r.id,
                "content": r.content,
                "from_date": r.from_date.isoformat(),
                "to_date": r.to_date.isoformat(),
            }
            if r.similarity is not None:
                entry["similarity"] = round(r.similarity, 4)
            out.append(entry)
        return out

    return server
