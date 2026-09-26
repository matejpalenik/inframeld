"""Resolve a verified human identity to an Inframeld access context."""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Protocol

from inframeld_backend.access.application.access_authorizer import AccessContext
from inframeld_backend.access.domain.values import IdentityAuthority, IdentitySubject, PrincipalId
from inframeld_backend.shared.application.errors import AccessDeniedError


@dataclass(frozen=True, slots=True)
class VerifiedHumanIdentity:
    """Identify a human already verified by the authentication provider."""

    authority: IdentityAuthority
    subject: IdentitySubject


class HumanIdentityLinkReader(Protocol):
    """Look up an active local human by its verified identity pair."""

    @abstractmethod
    async def find_active_principal_id(self, identity: VerifiedHumanIdentity) -> PrincipalId | None:
        """Find the active human linked to this exact authority and subject"""
        ...


class HumanSessionResolver:
    """Turn a verified identity into the caller context used by Acccess."""

    def __init__(self, reader: HumanIdentityLinkReader) -> None:
        self._reader = reader

    async def resolve(self, identity: VerifiedHumanIdentity) -> AccessContext:
        """Deny identities without an active local human principal."""

        principal_id = await self._reader.find_active_principal_id(identity)

        if principal_id is None:
            raise AccessDeniedError()

        return AccessContext(actor_principal_id=principal_id)
