from enum import StrEnum


class ModelRole(StrEnum):
    GENERATION = "generation"
    EMBEDDING = "embedding"
    RERANKING = "reranking"
