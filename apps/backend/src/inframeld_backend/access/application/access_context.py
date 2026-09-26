"""Carry the authenticated local actor into application operations."""

from dataclasses import dataclass

from inframeld_backend.access.domain.principal import PrincipalId


@dataclass(frozen=True, slots=True)
class AccessContext:
    """Identify the authenticated principal without caching its changing permissions."""

    actor_principal_id: PrincipalId
