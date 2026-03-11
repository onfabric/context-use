from __future__ import annotations

from datetime import UTC, datetime

from context_use.etl.core.types import ThreadRow
from context_use.etl.payload.models import (
    CURRENT_THREAD_PAYLOAD_VERSION,
    Application,
    Collection,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
)
from context_use.evals.longmemeval.schema import Question, Turn

PROVIDER = "longmemeval"
INTERACTION_TYPE = "longmemeval_sessions"

_APPLICATION = Application(name="assistant")  # type: ignore[reportCallIssue]


def _parse_date(date_str: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    return datetime.now(UTC)


def _make_collection(session_id: str) -> Collection:
    kwargs: dict[str, str] = {
        "type": "Collection",
        "id": f"https://longmemeval.bench/{session_id}",
    }
    return Collection(**kwargs)  # type: ignore[reportCallIssue]


def _turn_to_payload(
    turn: Turn,
    session_id: str,
) -> FibreSendMessage | FibreReceiveMessage | None:
    context = _make_collection(session_id)
    message = FibreTextMessage(content=turn.content, context=context)  # type: ignore[reportCallIssue]

    if turn.role == "user":
        return FibreSendMessage(  # type: ignore[reportCallIssue]
            object=message,
            target=_APPLICATION,
        )
    elif turn.role == "assistant":
        return FibreReceiveMessage(  # type: ignore[reportCallIssue]
            object=message,
            actor=_APPLICATION,
        )
    return None


def question_to_thread_rows(question: Question) -> list[ThreadRow]:
    """Convert all haystack sessions for a question into ThreadRows.

    Each turn in each session becomes one ThreadRow, mirroring how
    ChatGPT conversations are ingested: individual messages as threads,
    grouped by session/collection ID for memory generation.
    """
    rows: list[ThreadRow] = []

    for idx, session in enumerate(question.haystack_sessions):
        session_id = (
            question.haystack_session_ids[idx]
            if idx < len(question.haystack_session_ids)
            else f"session_{idx}"
        )
        session_date = (
            _parse_date(question.haystack_dates[idx])
            if idx < len(question.haystack_dates)
            else datetime.now(UTC)
        )

        for turn_idx, turn in enumerate(session):
            payload = _turn_to_payload(turn, session_id)
            if payload is None:
                continue

            asat = session_date.replace(
                hour=min(turn_idx, 23),
                minute=min(turn_idx % 60, 59),
            )

            rows.append(
                ThreadRow(
                    unique_key=payload.unique_key(),
                    provider=PROVIDER,
                    interaction_type=INTERACTION_TYPE,
                    preview=payload.get_preview(PROVIDER) or "",
                    payload=payload.to_dict(),
                    version=CURRENT_THREAD_PAYLOAD_VERSION,
                    asat=asat,
                )
            )

    return rows
