from enum import StrEnum


class _BaseModel(StrEnum):
    def __init__(self, value: str) -> None:
        self._provider = self.value.split("/", 1)[0]
        self._model = self.value.split("/", 1)[-1]
        super().__init__()

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model


class OpenAIModel(_BaseModel):
    GPT_4O = "openai/gpt-4o"
    GPT_5_2 = "openai/gpt-5.2"


class VertexAIModel(_BaseModel):
    GEMINI_2_5_FLASH = "vertex_ai/gemini-2.5-flash"


type Model = OpenAIModel | VertexAIModel


class OpenAIEmbeddingModel(_BaseModel):
    TEXT_EMBEDDING_3_LARGE = "openai/text-embedding-3-large"
    TEXT_EMBEDDING_3_SMALL = "openai/text-embedding-3-small"


class VertexAIEmbeddingModel(_BaseModel):
    TEXT_EMBEDDING_004 = "vertex_ai/text-embedding-004"


type EmbeddingModel = OpenAIEmbeddingModel | VertexAIEmbeddingModel
