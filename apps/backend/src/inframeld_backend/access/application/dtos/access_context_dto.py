"""Carry the authenticated local actor into application operations."""

from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class AccessContextDTO:
    """Identify the caller after authentication. Project permissions are checked separately."""

    actor_principal_id: PrincipalId
