from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience


@dataclass(frozen=True, slots=True)
class HumanOAuthConsentDetailsDTO:
    """Give the account UI checked display data, not reusable approval authority."""

    identity: VerifiedHumanIdentityDTO
    client_id: OAuthClientId
    installation: HumanAPIAudience
    scopes: tuple[HumanOAuthScope, ...]
    audiences: tuple[HumanAPIAudience, ...]
    approval_required: bool
    remember_consent_seconds: int
