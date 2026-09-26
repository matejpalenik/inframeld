"""Decide project visibility from current account, project, and membership state."""

from inframeld_backend.access.domain.principal import PrincipalStatus
from inframeld_backend.access.domain.project_values import ProjectStatus


def may_view_project(
    *,
    principal_status: PrincipalStatus,
    project_status: ProjectStatus,
    is_project_member: bool,
) -> bool:
    """Require an active principal and project, plus current membership.

    The caller must first resolve a project in the principal's organization.
    Visibility does not require an action grant. It determines whether an
    authorization failure may disclose that the project exists.
    """
    return (
        principal_status is PrincipalStatus.ACTIVE
        and project_status is ProjectStatus.ACTIVE
        and is_project_member
    )
