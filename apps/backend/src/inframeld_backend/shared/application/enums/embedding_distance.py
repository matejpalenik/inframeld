from enum import StrEnum


class EmbeddingDistance(StrEnum):
    COSINE = "cosine"
    DOT_PRODUCT = "dot-product"
    EUCLIDEAN = "euclidean"
