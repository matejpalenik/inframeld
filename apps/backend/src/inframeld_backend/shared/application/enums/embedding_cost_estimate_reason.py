from enum import StrEnum


class EmbeddingCostEstimateReason(StrEnum):
    """Identify why the single embedding input category could not be estimated."""

    UNSUPPORTED_MODEL = "unsupported-model"
    UNVERIFIED_BINDING = "unverified-binding"
    MISSING_INPUT_QUANTITY = "missing-input-quantity"
    MISMATCHED_INPUT_QUANTITY = "mismatched-input-quantity"
    AMOUNT_OUT_OF_RANGE = "amount-out-of-range"
