"""Carry current stored state for a project in the caller's organization."""

from dataclasses import dataclass

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class ProjectActionFactsDTO:
    """Carry the stored state for one project in the caller's organization.

    The reader supplies the matched organization, account/project status,
    membership, and requested grant. The service decides visibility and permission.
    """

    organization_id: OrganizationId
    principal_status: PrincipalStatus
    project_status: ProjectStatus
    is_project_member: bool
    has_exact_action_grant: bool
