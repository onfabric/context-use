from __future__ import annotations

import pytest

from context_use.llm.litellm.config import (
    BaseLlmConfig,
    OpenAIConfig,
    VertexAIConfig,
)
from context_use.llm.litellm.models import (
    OpenAIEmbeddingModel,
    OpenAIModel,
    VertexAIEmbeddingModel,
    VertexAIModel,
)


class TestOpenAIConfig:
    def test_implements_base(self) -> None:
        config = OpenAIConfig(
            model=OpenAIModel.GPT_5_2,
            embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
            api_key="sk-test",
        )
        assert isinstance(config, BaseLlmConfig)

    def test_model_property(self) -> None:
        config = OpenAIConfig(
            model=OpenAIModel.GPT_5_2,
            embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
            api_key="sk-test",
        )
        assert config.model == "openai/gpt-5.2"
        assert config.embedding_model == "openai/text-embedding-3-large"

    def test_litellm_params(self) -> None:
        config = OpenAIConfig(
            model=OpenAIModel.GPT_5_2,
            embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
            api_key="sk-test",
        )
        assert config.litellm_params() == {"api_key": "sk-test"}

    def test_slots_prevent_mutation(self) -> None:
        config = OpenAIConfig(
            model=OpenAIModel.GPT_5_2,
            embedding_model=OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE,
            api_key="sk-test",
        )
        with pytest.raises(AttributeError):
            config.foo = "bar"  # type: ignore[attr-defined]


class TestVertexAIConfig:
    def test_implements_base(self) -> None:
        config = VertexAIConfig(
            model=VertexAIModel.GEMINI_2_5_PRO,
            embedding_model=VertexAIEmbeddingModel.TEXT_EMBEDDING_005,
            vertex_project="proj",
            vertex_location="us-central1",
            vertex_credentials='{"type": "service_account"}',
            batch_artifacts_gcs_bucket_name="my-bucket",
        )
        assert isinstance(config, BaseLlmConfig)

    def test_litellm_params(self) -> None:
        config = VertexAIConfig(
            model=VertexAIModel.GEMINI_2_5_PRO,
            embedding_model=VertexAIEmbeddingModel.TEXT_EMBEDDING_005,
            vertex_project="proj",
            vertex_location="eu-west1",
            vertex_credentials='{"type": "service_account"}',
            batch_artifacts_gcs_bucket_name="my-bucket",
        )
        assert config.litellm_params() == {
            "vertex_project": "proj",
            "vertex_location": "eu-west1",
            "vertex_credentials": '{"type": "service_account"}',
            "gcs_bucket_name": "my-bucket",
        }
