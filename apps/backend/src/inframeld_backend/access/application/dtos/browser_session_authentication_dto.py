from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


@dataclass(frozen=True, slots=True)
class BrowserSessionAuthenticationDTO:
    """Record which identity the browser authenticator verified, without its cookie."""

    identity: VerifiedHumanIdentityDTO
