"""Carry current stored state for a project in the caller's organization."""

from dataclasses import dataclass

from inframeld_backend.access.domain.principal import PrincipalStatus
from inframeld_backend.access.domain.project_values import ProjectStatus


@dataclass(frozen=True, slots=True)
class CurrentActionFacts:
    """Describe account/project status, membership, and the exact requested grant.

    These facts do not establish visibility or permission. Domain policies make
    those decisions; the reader must first enforce the organization boundary.
    """

    principal_status: PrincipalStatus
    project_status: ProjectStatus
    is_project_member: bool
    has_exact_action_grant: bool
