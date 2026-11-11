from enum import StrEnum


class HumanIdentityLinkState(StrEnum):
    """Distinguish authoritative absence from a coherent or damaged local link."""

    UNLINKED = "unlinked"
    LINKED = "linked"
    INCOHERENT = "incoherent"
