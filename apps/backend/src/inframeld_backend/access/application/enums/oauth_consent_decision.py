from enum import StrEnum


class OAuthConsentDecision(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
