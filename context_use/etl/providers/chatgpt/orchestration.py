from __future__ import annotations

from context_use.etl.core.etl import OrchestrationStrategy


class ChatGPTOrchestrationStrategy(OrchestrationStrategy):
    """Discovers ChatGPT ETL tasks from extracted archive files.

    Looks for ``conversations.json`` at the root of the archive.
    """

    MANIFEST_MAP = {
        "conversations.json": "chatgpt_conversations",
    }
