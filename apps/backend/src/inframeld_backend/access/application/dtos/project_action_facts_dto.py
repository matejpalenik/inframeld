"""Carry current stored state for a project in the caller's organization."""

from dataclasses import dataclass

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus


@dataclass(frozen=True, slots=True)
class ProjectActionFactsDTO:
    """Carry the stored state for one project in the caller's organization.

    The reader supplies account/project status, membership, and the requested
    grant. The service applies policies to decide visibility and permission.
    """

    principal_status: PrincipalStatus
    project_status: ProjectStatus
    is_project_member: bool
    has_exact_action_grant: bool
