from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


@dataclass(frozen=True, slots=True)
class HumanSuspensionCleanupDispatchDTO:
    """Carry the exact identity and remaining live budget for one marked effect."""

    identity: VerifiedHumanIdentityDTO
    remaining_seconds: float
