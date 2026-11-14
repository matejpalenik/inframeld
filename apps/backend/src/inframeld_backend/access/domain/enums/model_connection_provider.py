from enum import StrEnum


class ModelConnectionProvider(StrEnum):
    OPENAI = "openai"
    OPENAI_COMPATIBLE = "openai-compatible"
    OLLAMA = "ollama"
