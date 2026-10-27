from dataclasses import dataclass
from typing import Self, override

from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True, eq=False)
class ProjectActionGrant:
    """One project action assignment whose identity survives level changes.

    Historical attribution may be absent. New assignments use the factory to
    record the assigning principal. The owning membership controls its grants.
    """

    project_id: ProjectId
    recipient_principal_id: PrincipalId
    action_id: ActionId
    level: ProjectGrantLevel
    assigned_by_principal_id: PrincipalId | None

    @classmethod
    def create_use_only(
        cls,
        *,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
        assigned_by_principal_id: PrincipalId,
    ) -> Self:
        """Create an attributed assignment without delegation rights."""
        return cls(
            project_id,
            recipient_principal_id,
            action_id,
            ProjectGrantLevel.USE_ONLY,
            assigned_by_principal_id,
        )

    @property
    def identity(self) -> tuple[ProjectId, PrincipalId, ActionId]:
        return self.project_id, self.recipient_principal_id, self.action_id

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectActionGrant):
            return NotImplemented
        return self.identity == other.identity

    @override
    def __hash__(self) -> int:
        return hash(self.identity)
