from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class OrganizationGrantTargetDTO:
    organization_id: OrganizationId
