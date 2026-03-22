from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Application,
    Collection,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
)

PROVIDER = "unknown"
INTERACTION_TYPE = "unknown_conversations"

_APPLICATION = Application(name="assistant")  # type: ignore[reportCallIssue]


def _extract_text(content: str | list[dict[str, Any]] | None) -> str | None:
    if isinstance(content, str):
        return content or None
    if isinstance(content, list):
        texts = [
            part["text"]
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        joined = " ".join(texts)
        return joined or None
    return None


def _build_payload(
    role: str,
    text: str,
    *,
    session_id: str | None,
    published: datetime,
) -> FibreSendMessage | FibreReceiveMessage:
    context = None
    if session_id:
        context = Collection(id=f"https://{PROVIDER}/session/{session_id}")  # type: ignore[reportCallIssue]

    message = FibreTextMessage(content=text, context=context)  # type: ignore[reportCallIssue]

    if role == "user":
        return FibreSendMessage(  # type: ignore[reportCallIssue]
            object=message,
            target=_APPLICATION,
            published=published,
        )
    return FibreReceiveMessage(  # type: ignore[reportCallIssue]
        object=message,
        actor=_APPLICATION,
        published=published,
    )


def messages_to_thread_rows(
    messages: list[dict[str, Any]],
    *,
    session_id: str | None = None,
    now: datetime | None = None,
) -> list[ThreadRow]:
    ts = now or datetime.now(UTC)
    rows: list[ThreadRow] = []

    for msg in messages:
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue

        text = _extract_text(msg.get("content"))
        if not text:
            continue

        payload = _build_payload(role, text, session_id=session_id, published=ts)

        rows.append(
            ThreadRow(
                unique_key=payload.unique_key(),
                provider=PROVIDER,
                interaction_type=INTERACTION_TYPE,
                preview=payload.get_preview() or "",
                payload=payload.to_dict(),
                version=CURRENT_THREAD_PAYLOAD_VERSION,
                asat=ts,
                collection_id=payload.get_collection(),
            )
        )

    return rows
