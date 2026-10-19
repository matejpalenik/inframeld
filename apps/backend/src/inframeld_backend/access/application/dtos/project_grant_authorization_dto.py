from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class ProjectGrantAuthorizationDTO:
    """Current scope and revision established by grant authorization.

    Use this result within the same transaction that holds the Access locks.
    It does not establish permission for a later request.
    """

    organization_id: OrganizationId
    project_access_revision: int
