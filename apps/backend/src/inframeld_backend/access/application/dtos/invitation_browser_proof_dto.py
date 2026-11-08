from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)


@dataclass(frozen=True, slots=True)
class InvitationBrowserProofDTO:
    """Carry current identity and a payload-free stored password-verifier observation.

    True means a current stored nonempty verifier was observed, not password
    usability, current-session authentication or permanent completion history.
    None means not observed or unavailable. Only fresh activation requires the
    fact. Provider identity/configuration/hash objects never belong in this DTO.
    """

    identity: VerifiedHumanIdentityDTO
    password_completed: bool | None
