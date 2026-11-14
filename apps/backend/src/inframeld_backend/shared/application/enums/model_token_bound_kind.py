from enum import StrEnum


class ModelTokenBoundKind(StrEnum):
    EXACT = "exact"
    CONSERVATIVE_UPPER_BOUND = "conservative-upper-bound"
