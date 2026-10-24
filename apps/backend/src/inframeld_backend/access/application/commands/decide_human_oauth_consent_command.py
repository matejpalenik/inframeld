from dataclasses import dataclass

from inframeld_backend.access.application.enums.oauth_consent_decision import OAuthConsentDecision
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)
from inframeld_backend.shared.application.commands.command import Command


@dataclass(frozen=True, slots=True)
class DecideHumanOAuthConsentCommand(Command):
    challenge: OAuthConsentChallenge
    decision: OAuthConsentDecision
    remember: bool = False

    def __post_init__(self) -> None:
        if type(self.decision) is not OAuthConsentDecision or type(self.remember) is not bool:
            raise ValueError(
                "Consent requires an allow/deny decision and a boolean remember choice."
            )
