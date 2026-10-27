from dataclasses import dataclass

from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject


@dataclass(frozen=True, slots=True)
class HumanOAuthConsentRequestDTO:
    """Describe Hydra's request, before Inframeld verifies who may approve it."""

    subject: IdentitySubject
    client_id: OAuthClientId
    scopes: tuple[HumanOAuthScope, ...]
    audiences: tuple[HumanAPIAudience, ...]
    skip: bool
