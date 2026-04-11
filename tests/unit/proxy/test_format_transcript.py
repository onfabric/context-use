from __future__ import annotations

from datetime import UTC, datetime

from context_use.memories.prompt.conversation import format_transcript
from context_use.models.thread import Thread
from context_use.proxy.threads import messages_to_thread_rows


def _make_thread(
    content: str,
    role: str = "user",
    **kwargs: object,
) -> Thread:
    ts = datetime(2025, 6, 15, 10, 30, tzinfo=UTC)
    rows = messages_to_thread_rows(
        [{"role": role, "content": content}],
        now=ts,
    )
    return Thread(
        unique_key=rows[0].unique_key,
        provider=rows[0].provider,
        interaction_type=rows[0].interaction_type,
        payload=rows[0].payload,
        version=rows[0].version,
        asat=rows[0].asat,
    )


class TestFormatTranscript:
    def test_basic_transcript(self) -> None:
        threads = [
            _make_thread("What is 2+2?", role="user"),
            _make_thread("4", role="assistant"),
        ]
        result = format_transcript(threads)

        assert "## Transcript" in result
        assert "[ME " in result
        assert "[ASSISTANT " in result
        assert "What is 2+2?" in result
        assert "4" in result

    def test_empty_threads(self) -> None:
        result = format_transcript([])
        assert "## Transcript" in result

    def test_custom_content_fn(self) -> None:
        threads = [_make_thread("Hello world", role="user")]
        result = format_transcript(threads, content_fn=lambda t: "CUSTOM")
        assert "CUSTOM" in result
        assert "Hello world" not in result
