from enum import StrEnum


class JobContinuationDisposition(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    NOT_ESTABLISHED = "not_established"
