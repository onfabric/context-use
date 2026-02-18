from enum import StrEnum


class OpenAIModel(StrEnum):
    GPT_4O = "openai/gpt-4o"
    GPT_4O_MINI = "openai/gpt-4o-mini"
    GPT_4_1 = "openai/gpt-4.1"
    GPT_4_1_MINI = "openai/gpt-4.1-mini"
    GPT_4_1_NANO = "openai/gpt-4.1-nano"


class GeminiModel(StrEnum):
    GEMINI_25_FLASH = "gemini/gemini-2.5-flash"
    GEMINI_25_PRO = "gemini/gemini-2.5-pro"
