"""Identify the project whose exact action authority is being evaluated."""

from dataclasses import dataclass

from inframeld_backend.access.domain.project_values import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectActionTarget:
    """Scope a project action without an independently supplied kind or mismatched UUID."""

    project_id: ProjectId
