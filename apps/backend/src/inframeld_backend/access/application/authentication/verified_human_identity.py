"""Represent the identity returned by a successful external session verification."""

from dataclasses import dataclass

from inframeld_backend.access.domain.identity_values import IdentityAuthority, IdentitySubject


@dataclass(frozen=True, slots=True)
class VerifiedHumanIdentity:
    """Carry a verified authority and subject; local admission still needs checking."""

    authority: IdentityAuthority
    subject: IdentitySubject
