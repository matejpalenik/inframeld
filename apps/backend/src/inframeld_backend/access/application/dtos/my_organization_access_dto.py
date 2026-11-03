from dataclasses import dataclass

from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


@dataclass(frozen=True, slots=True)
class MyOrganizationAccessDTO:
    """Return the human's stored assignments without promising later authority."""

    organization_id: OrganizationId
    principal_id: PrincipalId
    access_revision: int
    grants: tuple[OrganizationActionGrantDTO, ...]
