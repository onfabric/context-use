from context_use.llm.litellm.models import OpenAIModel, VertexAIModel


class TestProviderId:
    def test_openai_prefix(self) -> None:
        assert OpenAIModel.GPT_4O.provider_name == "openai"

    def test_vertex_ai_prefix(self) -> None:
        assert VertexAIModel.GEMINI_2_5_FLASH.provider_name == "vertex_ai"


class TestModelId:
    def test_strips_openai(self) -> None:
        assert OpenAIModel.GPT_4O.model_name == "gpt-4o"

    def test_strips_vertex_ai(self) -> None:
        assert VertexAIModel.GEMINI_2_5_FLASH.model_name == "gemini-2.5-flash"
