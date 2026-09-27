from enum import StrEnum


class OperationReplayKind(StrEnum):
    """Identify the safe outcome the owning workflow can reconstruct."""

    ASYNC_JOB = "async_job"
    SAFE_RESULT = "safe_result"
    ISSUED_SECRET = "issued_secret"
    ANSWER_RECEIPT = "answer_receipt"
