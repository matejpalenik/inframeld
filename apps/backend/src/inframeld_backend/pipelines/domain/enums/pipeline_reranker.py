from enum import StrEnum


class PipelineReranker(StrEnum):
    """Select the reranker supported by this saved configuration component."""

    NONE = "none"
