from enum import StrEnum


class _BaseModel(StrEnum):
    def __init__(self, value: str) -> None:
        self._provider_name = self.value.split("/", 1)[0]
        self._model_name = self.value.split("/", 1)[-1]
        super().__init__()

    @property
    def provider_name(self) -> str:
        return self._provider_name

    @property
    def model_name(self) -> str:
        return self._model_name


class OpenAIModel(_BaseModel):
    GPT_5_2 = "openai/gpt-5.2"


class VertexAIModel(_BaseModel):
    GEMINI_2_5_FLASH = "vertex_ai/gemini-2.5-flash"


type Model = OpenAIModel | VertexAIModel


class OpenAIEmbeddingModel(_BaseModel):
    TEXT_EMBEDDING_3_LARGE = "openai/text-embedding-3-large"


class VertexAIEmbeddingModel(_BaseModel):
    TEXT_EMBEDDING_005 = "vertex_ai/text-embedding-005"


type EmbeddingModel = OpenAIEmbeddingModel | VertexAIEmbeddingModel
