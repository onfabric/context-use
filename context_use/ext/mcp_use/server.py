# pyright: reportMissingImports=false, reportCallIssue=false, reportGeneralTypeIssues=false
"""MCP server factory for context_use (requires the ``mcp-use`` extra).

Usage::

    from context_use.db.postgres import PostgresBackend
    from context_use.ext.mcp_use.server import create_server

    db = PostgresBackend(...)
    server = create_server(db=db, openai_api_key="sk-...")
    server.run(transport="streamable-http")
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from context_use.db.base import DatabaseBackend
from context_use.search.memories import MemorySearchResult, search_memories

if TYPE_CHECKING:
    from mcp_use.server import MCPServer


def _format_results(results: list[MemorySearchResult]) -> list[dict]:
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


def create_server(
    db: DatabaseBackend,
    openai_api_key: str | None = None,
    *,
    name: str = "context-use",
    version: str = "0.1.0",
) -> MCPServer:
    """Build an MCPServer with the search_memories tool registered.

    Requires the ``mcp-use`` extra (``pip install context-use[mcp-use]``).

    Args:
        db: Database backend to query against.
        openai_api_key: Required for semantic search queries.
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
            "Memory search server. Use the search_memories tool to find "
            "user memories by semantic query, time range, or both."
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

        results = await search_memories(
            db,
            query=query,
            from_date=parsed_from,
            to_date=parsed_to,
            top_k=top_k,
            openai_api_key=openai_api_key,
        )

        return _format_results(results)

    return server
