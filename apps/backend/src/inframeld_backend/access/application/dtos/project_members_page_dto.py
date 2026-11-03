from dataclasses import dataclass

from inframeld_backend.access.application.dtos.project_member_dto import ProjectMemberDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectMembersPageDTO:
    """Carry one authorized observation, not permission or a traversal snapshot."""

    project_id: ProjectId
    access_revision: int
    items: tuple[ProjectMemberDTO, ...]
    next_cursor: str | None
