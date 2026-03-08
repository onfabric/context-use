from __future__ import annotations

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
    """Build an MCPServer with the full memory tool set registered.

    Requires the ``mcp-use`` extra (``uv sync --extra mcp-use``).

    Args:
        ctx: A fully configured :class:`ContextUse` instance.
        name: Server name exposed to MCP clients.
        version: Server version exposed to MCP clients.
    """
    try:
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
            "Personal memory server. Use search_memories to recall relevant "
            "episodes, list_memories to survey a narrow time window, and the "
            "write tools (update_memory, create_memory, archive_memories) to "
            "keep the memory store accurate and up to date."
        ),
    )

    for fn in ctx.make_tools():
        title = fn.__name__.replace("_", " ").title()
        server.tool(title=title)(fn)

    return server
