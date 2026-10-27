import pytest

from inframeld_backend.access.application.commands.decide_human_oauth_consent_command import (
    DecideHumanOAuthConsentCommand,
)
from inframeld_backend.access.application.enums.oauth_consent_decision import OAuthConsentDecision
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)


@pytest.mark.parametrize("decision,remember", [(OAuthConsentDecision.ALLOW, 1), ("deny", False)])
def test_invalid_internal_input_cannot_accidentally_become_an_allow(
    decision: OAuthConsentDecision, remember: bool
) -> None:
    with pytest.raises(ValueError):
        DecideHumanOAuthConsentCommand(OAuthConsentChallenge("secret"), decision, remember)
