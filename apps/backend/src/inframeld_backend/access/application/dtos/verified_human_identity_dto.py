"""Represent the identity returned by a successful external session verification."""

from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject


@dataclass(frozen=True, slots=True)
class VerifiedHumanIdentityDTO:
    """Carry the identity verified by the provider. Local account admission is still required."""

    authority: IdentityAuthority
    subject: IdentitySubject
