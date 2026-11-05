from enum import StrEnum


class OperationDispatchEstablishment(StrEnum):
    """Keep an unproved dispatch outcome distinct from confirmed admission."""

    NOT_ESTABLISHED = "not_established"
