from enum import StrEnum


class ReviewedModelProperty(StrEnum):
    CONTEXT_TOKENS = "context_tokens"
    TOKEN_BOUND = "token_bound"
    OUTPUT_TOKENS = "output_tokens"
    STRUCTURED_OUTPUT = "structured_output"
    EMBEDDING_DIMENSIONS = "embedding_dimensions"
    EMBEDDING_NORMALIZATION = "embedding_normalization"
    EMBEDDING_DISTANCE = "embedding_distance"
    DOCUMENT_PREFIX = "document_prefix"
    QUERY_PREFIX = "query_prefix"
    MAXIMUM_CANDIDATES = "maximum_candidates"
