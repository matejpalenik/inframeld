from dataclasses import dataclass

from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)


@dataclass(frozen=True, slots=True)
class InspectHumanOAuthConsentQuery:
    challenge: OAuthConsentChallenge
