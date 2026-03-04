# pyright: reportMissingImports=false, reportCallIssue=false, reportGeneralTypeIssues=false
"""MCP server factory for context_use (requires the ``mcp-use`` extra).

Usage::

    from context_use import ContextUse
    from context_use.ext.mcp_use.server import create_server

    ctx = ContextUse(storage=..., store=..., llm_client=...)
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
    """Build an MCPServer with memory search tools registered.

    Requires the ``mcp-use`` extra (``uv sync --extra mcp-use``).

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
            "Install it with: uv sync --extra mcp-use"
        ) from None

    server = _MCPServer(
        name=name,
        version=version,
        instructions=(
            "Context server. Use search_memories to recall specific episodes "
            "from the user's memory archive."
        ),
    )

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
