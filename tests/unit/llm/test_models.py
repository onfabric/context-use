from context_use.llm.litellm.models import (
    OpenAIEmbeddingModel,
    OpenAIModel,
    VertexAIEmbeddingModel,
    VertexAIModel,
)


class TestProviderNameModel:
    def test_openai_prefix(self) -> None:
        assert OpenAIModel.GPT_5_2.provider_name == "openai"

    def test_vertex_ai_prefix(self) -> None:
        assert VertexAIModel.GEMINI_2_5_FLASH.provider_name == "vertex_ai"


class TestModelNameModel:
    def test_strips_openai(self) -> None:
        assert OpenAIModel.GPT_5_2.model_name == "gpt-4o"

    def test_strips_vertex_ai(self) -> None:
        assert VertexAIModel.GEMINI_2_5_FLASH.model_name == "gemini-2.5-flash"


class TestProviderNameEmbeddingModel:
    def test_openai_prefix(self) -> None:
        assert OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE.provider_name == "openai"

    def test_vertex_ai_prefix(self) -> None:
        assert VertexAIEmbeddingModel.TEXT_EMBEDDING_005.provider_name == "vertex_ai"


class TestModelNameEmbeddingModel:
    def test_strips_openai(self) -> None:
        assert (
            OpenAIEmbeddingModel.TEXT_EMBEDDING_3_LARGE.model_name
            == "text-embedding-3-large"
        )

    def test_strips_vertex_ai(self) -> None:
        assert (
            VertexAIEmbeddingModel.TEXT_EMBEDDING_005.model_name == "text-embedding-005"
        )
