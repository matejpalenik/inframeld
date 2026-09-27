"""Identify the project whose exact action authority is being evaluated."""

from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectActionTargetDTO:
    """Select the project to authorize. This does not prove that it exists or is visible."""

    project_id: ProjectId
