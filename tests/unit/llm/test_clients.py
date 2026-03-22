from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from context_use.llm.base import EmbedItem, PromptItem
from context_use.llm.litellm.clients import (
    LiteLLMBatchClient,
    LiteLLMSyncClient,
    _build_batch_jsonl_line,
    _build_embed_batch_jsonl_line,
)
from context_use.llm.litellm.config import OpenAIConfig, VertexAIConfig
from context_use.llm.litellm.models import (
    OpenAIEmbeddingModel,
    OpenAIModel,
    VertexAIEmbeddingModel,
    VertexAIModel,
)


class _SampleSchema(BaseModel):
    answer: str


def _make_prompt(item_id: str = "test-1", prompt: str = "hello") -> PromptItem:
    return PromptItem(
        item_id=item_id,
        prompt=prompt,
        response_schema=_SampleSchema.model_json_schema(),
    )


_OPENAI_CONFIG = OpenAIConfig(
    model=OpenAIModel.GPT_5_2,
    embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
    api_key="sk-test",
)

_VERTEX_CONFIG = VertexAIConfig(
    model=VertexAIModel.GEMINI_2_5_PRO,
    embedding_model=VertexAIEmbeddingModel.TEXT_EMBEDDING_005,
    vertex_project="my-project",
    vertex_location="us-central1",
)


class TestBuildBatchJsonlLine:
    def test_strips_openai_prefix(self) -> None:
        line = _build_batch_jsonl_line(_make_prompt(), OpenAIModel.GPT_5_2)
        assert line["body"]["model"] == "gpt-5.2"

    def test_strips_vertex_ai_prefix(self) -> None:
        line = _build_batch_jsonl_line(_make_prompt(), VertexAIModel.GEMINI_2_5_PRO)
        assert line["body"]["model"] == "gemini-2.5-pro"

    def test_custom_id_matches(self) -> None:
        line = _build_batch_jsonl_line(_make_prompt("my-id"), OpenAIModel.GPT_5_2)
        assert line["custom_id"] == "my-id"


class TestBuildEmbedBatchJsonlLine:
    def test_strips_provider_prefix(self) -> None:
        item = EmbedItem(item_id="e1", text="hello")
        line = _build_embed_batch_jsonl_line(
            item, OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE
        )
        assert line["body"]["model"] == "text-embedding-3-large"


class TestLiteLLMBaseInit:
    def test_openai_config_stores_params(self) -> None:
        client = LiteLLMSyncClient(_OPENAI_CONFIG)
        assert client._litellm_params["api_key"] == "sk-test"

    def test_vertex_config_stores_params(self) -> None:
        client = LiteLLMSyncClient(_VERTEX_CONFIG)
        assert client._litellm_params["vertex_project"] == "my-project"
        assert "api_key" not in client._litellm_params

    def test_config_property_returns_config(self) -> None:
        client = LiteLLMSyncClient(_OPENAI_CONFIG)
        assert client.config is _OPENAI_CONFIG

    def test_provider_property_openai(self) -> None:
        client = LiteLLMSyncClient(_OPENAI_CONFIG)
        assert client._provider_name == "openai"

    def test_provider_property_vertex_ai(self) -> None:
        client = LiteLLMSyncClient(_VERTEX_CONFIG)
        assert client._provider_name == "vertex_ai"


class TestLiteLLMSyncClientCompletion:
    @pytest.mark.asyncio
    async def test_structured_completion_forwards_params(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"answer": "42"})

        client = LiteLLMSyncClient(_VERTEX_CONFIG)

        with patch("context_use.llm.litellm.clients.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            result = await client.structured_completion(_make_prompt(), _SampleSchema)

            call_kwargs = mock_litellm.acompletion.call_args
            assert call_kwargs.kwargs["vertex_project"] == "my-project"
            assert result.answer == "42"

    @pytest.mark.asyncio
    async def test_embed_query_forwards_params(self) -> None:
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]

        client = LiteLLMSyncClient(_OPENAI_CONFIG)

        with patch("context_use.llm.litellm.clients.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)
            result = await client.embed_query("hello")

            call_kwargs = mock_litellm.aembedding.call_args
            assert call_kwargs.kwargs["api_key"] == "sk-test"
            assert call_kwargs.kwargs["model"] == str(
                OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE
            )
            assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_sync_batch_submit_and_get(self) -> None:
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = json.dumps({"answer": "ok"})

        client = LiteLLMSyncClient(_OPENAI_CONFIG)

        with patch("context_use.llm.litellm.clients.litellm") as mock_litellm:
            mock_litellm.acompletion = AsyncMock(return_value=mock_response)
            key = await client.batch_submit("b1", [_make_prompt("p1")])
            results = await client.batch_get_results(key, _SampleSchema)

        assert results is not None
        assert "p1" in results
        assert results["p1"].answer == "ok"

    @pytest.mark.asyncio
    async def test_sync_embed_batch_submit_and_get(self) -> None:
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [1.0, 2.0]}]

        client = LiteLLMSyncClient(_OPENAI_CONFIG)

        with patch("context_use.llm.litellm.clients.litellm") as mock_litellm:
            mock_litellm.aembedding = AsyncMock(return_value=mock_response)
            key = await client.embed_batch_submit(
                "eb1", [EmbedItem(item_id="e1", text="hi")]
            )
            results = await client.embed_batch_get_results(key)

        assert results is not None
        assert results["e1"] == [1.0, 2.0]


class TestLiteLLMBatchClientProvider:
    @pytest.mark.asyncio
    async def test_batch_submit_uses_provider_from_model(self) -> None:
        mock_file = MagicMock()
        mock_file.id = "file-123"
        mock_batch = MagicMock()
        mock_batch.id = "batch-456"

        client = LiteLLMBatchClient(_VERTEX_CONFIG)

        with patch("context_use.llm.litellm.clients.litellm") as mock_litellm:
            mock_litellm.acreate_file = AsyncMock(return_value=mock_file)
            mock_litellm.acreate_batch = AsyncMock(return_value=mock_batch)

            result = await client.batch_submit("b1", [_make_prompt()])

            file_kwargs = mock_litellm.acreate_file.call_args.kwargs
            assert file_kwargs["custom_llm_provider"] == "vertex_ai"
            assert file_kwargs["vertex_project"] == "my-project"

            batch_kwargs = mock_litellm.acreate_batch.call_args.kwargs
            assert batch_kwargs["custom_llm_provider"] == "vertex_ai"
            assert result == "batch-456"

    @pytest.mark.asyncio
    async def test_batch_get_results_uses_provider(self) -> None:
        mock_batch = MagicMock()
        mock_batch.status = "completed"
        mock_batch.output_file_id = "file-out"

        result_line = json.dumps(
            {
                "custom_id": "test-1",
                "response": {
                    "body": {
                        "choices": [
                            {"message": {"content": json.dumps({"answer": "ok"})}}
                        ]
                    }
                },
            }
        )
        mock_content = MagicMock()
        mock_content.content = result_line.encode("utf-8")

        client = LiteLLMBatchClient(_OPENAI_CONFIG)

        with patch("context_use.llm.litellm.clients.litellm") as mock_litellm:
            mock_litellm.aretrieve_batch = AsyncMock(return_value=mock_batch)
            mock_litellm.afile_content = AsyncMock(return_value=mock_content)

            results = await client.batch_get_results("batch-1", _SampleSchema)

            retrieve_kwargs = mock_litellm.aretrieve_batch.call_args.kwargs
            assert retrieve_kwargs["custom_llm_provider"] == "openai"
            assert retrieve_kwargs["api_key"] == "sk-test"

        assert results is not None
        assert results["test-1"].answer == "ok"
