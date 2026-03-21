from context_use.llm.litellm.models import OpenAIModel, VertexAIModel


class TestExtractProvider:
    def test_openai_prefix(self) -> None:
        assert OpenAIModel.GPT_4O.provider == "openai"

    def test_vertex_ai_prefix(self) -> None:
        assert VertexAIModel.GEMINI_2_5_FLASH.provider == "vertex_ai"


class TestStripProviderPrefix:
    def test_strips_openai(self) -> None:
        assert OpenAIModel.GPT_4O.model == "gpt-4o"

    def test_strips_vertex_ai(self) -> None:
        assert VertexAIModel.GEMINI_2_5_FLASH.model == "gemini-2.5-flash"
