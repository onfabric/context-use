from pydantic import BaseModel

PROVIDER = "claude"


class ClaudeConversationRecord(BaseModel):
    """Enriched extraction output for Claude conversations.

    Flattened from the nested ``chat_messages`` structure with
    conversation-level context (uuid, name) added by extraction.
    """

    role: str
    content: str
    created_at: str | None = None
    conversation_id: str | None = None
    conversation_title: str | None = None
    source: str | None = None
