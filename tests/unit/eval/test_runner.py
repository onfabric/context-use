from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import BaseModel

from context_use.eval.runner import ExtractionRun, GroupResult, run_extraction
from context_use.activitystreams.core import Collection
from context_use.etl.payload.models import (
    Application,
    FibreReceiveMessage,
    FibreSendMessage,
    FibreTextMessage,
)
from context_use.llm.base import (
    BaseLLMClient,
    BatchResults,
    EmbedBatchResults,
    EmbedItem,
    PromptItem,
)
from context_use.memories.prompt.base import Memory, MemorySchema
from context_use.models.thread import Thread


class FakeLLMClient(BaseLLMClient):
    def __init__(self, responses: dict[str, MemorySchema] | None = None) -> None:
        self._responses = responses or {}
        self._default = MemorySchema(memories=[
            Memory(content="Test memory about work.", from_date="2024-06-01", to_date="2024-06-01"),
        ])

    async def batch_submit(self, batch_id: str, prompts: list[PromptItem]) -> str:
        raise NotImplementedError

    async def batch_get_results[T: BaseModel](
        self, job_key: str, schema: type[T]
    ) -> BatchResults | None:
        raise NotImplementedError

    async def embed_batch_submit(self, batch_id: str, items: list[EmbedItem]) -> str:
        raise NotImplementedError

    async def embed_batch_get_results(self, job_key: str) -> EmbedBatchResults | None:
        raise NotImplementedError

    async def completion(self, prompt: str) -> str:
        return "ok"

    async def structured_completion[T: BaseModel](
        self, prompt: PromptItem, schema: type[T]
    ) -> T:
        result = self._responses.get(prompt.item_id, self._default)
        return schema.model_validate(result.model_dump())  # type: ignore[return-value]

    async def embed_query(self, text: str) -> list[float]:
        return [0.0] * 3072


_CONV_CTX = Collection(id="https://example.com/conv/1")  # pyright: ignore[reportCallIssue]


def _send_payload(content: str = "Can you help me with Python?") -> dict:
    msg = FibreTextMessage(content=content, context=_CONV_CTX)  # pyright: ignore[reportCallIssue]
    target = Application(name="ChatGPT")  # pyright: ignore[reportCallIssue]
    return FibreSendMessage(object=msg, target=target).to_dict()  # pyright: ignore[reportCallIssue]


def _recv_payload(content: str = "Sure, I can help!") -> dict:
    msg = FibreTextMessage(content=content, context=_CONV_CTX)  # pyright: ignore[reportCallIssue]
    actor = Application(name="ChatGPT")  # pyright: ignore[reportCallIssue]
    return FibreReceiveMessage(object=msg, actor=actor).to_dict()  # pyright: ignore[reportCallIssue]


def _make_thread(
    interaction_type: str = "chatgpt_conversations",
    unique_key: str = "test-key",
    preview: str = "test preview",
    is_send: bool = True,
) -> Thread:
    payload = _send_payload() if is_send else _recv_payload()
    return Thread(
        unique_key=unique_key,
        provider="chatgpt",
        interaction_type=interaction_type,
        preview=preview,
        payload=payload,
        version="1.0",
        asat=datetime(2024, 6, 1, 12, 0, tzinfo=UTC),
    )


class TestExtractionRun:
    def test_all_memories(self) -> None:
        run = ExtractionRun(results=[
            GroupResult(
                group_id="g1",
                interaction_type="test",
                thread_count=2,
                memories=[
                    Memory(content="a", from_date="2024-01-01", to_date="2024-01-01"),
                    Memory(content="b", from_date="2024-01-02", to_date="2024-01-02"),
                ],
            ),
            GroupResult(
                group_id="g2",
                interaction_type="test",
                thread_count=1,
                memories=[
                    Memory(content="c", from_date="2024-01-03", to_date="2024-01-03"),
                ],
            ),
        ])
        assert len(run.all_memories) == 3
        assert run.total_threads == 3

    def test_empty_run(self) -> None:
        run = ExtractionRun()
        assert run.all_memories == []
        assert run.total_threads == 0


@pytest.mark.asyncio
async def test_run_extraction_with_registered_provider() -> None:
    import context_use.providers.chatgpt  # noqa: F401

    threads = [
        _make_thread(unique_key=f"key-{i}")
        for i in range(3)
    ]
    client = FakeLLMClient()
    result = await run_extraction(threads, client)

    assert len(result.results) >= 1
    assert len(result.all_memories) >= 1


@pytest.mark.asyncio
async def test_run_extraction_skips_unknown_type() -> None:
    threads = [_make_thread(interaction_type="unknown_type")]
    client = FakeLLMClient()
    result = await run_extraction(threads, client)
    assert result.all_memories == []


@pytest.mark.asyncio
async def test_run_extraction_handles_llm_failure() -> None:
    import context_use.providers.chatgpt  # noqa: F401

    class FailingClient(FakeLLMClient):
        async def structured_completion[T: BaseModel](
            self, prompt: PromptItem, schema: type[T]
        ) -> T:
            raise RuntimeError("LLM failed")

    threads = [_make_thread()]
    client = FailingClient()
    result = await run_extraction(threads, client)
    assert result.all_memories == []
