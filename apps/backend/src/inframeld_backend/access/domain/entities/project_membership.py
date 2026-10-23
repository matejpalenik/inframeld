from typing import override

from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectMembership:
    """Own one member's complete collection of direct project action grants.

    Membership alone grants no action permission. Authorization separately checks
    current eligibility, delegation authority and project availability. This
    aggregate protects assignment transitions without persistence bookkeeping.
    """

    def __init__(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        principal_id: PrincipalId,
        principal_kind: PrincipalKind,
        grants: tuple[ProjectActionGrant, ...],
    ) -> None:
        grants_by_action: dict[ActionId, ProjectActionGrant] = {}
        for grant in grants:
            if grant.project_id != project_id or grant.recipient_principal_id != principal_id:
                raise ValueError("A grant belongs to another project membership.")
            if grant.action_id in grants_by_action:
                raise ValueError("A membership contains duplicate action grants.")
            if (
                principal_kind is PrincipalKind.APPLICATION
                and grant.level is ProjectGrantLevel.USE_AND_GRANT
            ):
                raise ValueError("Applications cannot hold delegation rights.")
            grants_by_action[grant.action_id] = grant

        self._organization_id = organization_id
        self._project_id = project_id
        self._principal_id = principal_id
        self._principal_kind = principal_kind
        self._grants = grants_by_action

    @property
    def identity(self) -> tuple[ProjectId, PrincipalId]:
        return self._project_id, self._principal_id

    @property
    def organization_id(self) -> OrganizationId:
        return self._organization_id

    @property
    def project_id(self) -> ProjectId:
        return self._project_id

    @property
    def principal_id(self) -> PrincipalId:
        return self._principal_id

    @property
    def principal_kind(self) -> PrincipalKind:
        return self._principal_kind

    @property
    def grants(self) -> tuple[ProjectActionGrant, ...]:
        """Expose immutable children without allowing collection mutation."""
        return tuple(self._grants.values())

    def assign_use_only_grant(
        self, *, action_id: ActionId, assigned_by_principal_id: PrincipalId
    ) -> None:
        """Assign a missing action without replacing or downgrading another grant.

        Raises:
            ProjectGrantAlreadyExistsError: The action is already assigned at
                either permission level. Leave the aggregate unchanged.
        """
        if action_id in self._grants:
            raise ProjectGrantAlreadyExistsError("This project action grant already exists.")
        grant = ProjectActionGrant.create_use_only(
            project_id=self._project_id,
            recipient_principal_id=self._principal_id,
            action_id=action_id,
            assigned_by_principal_id=assigned_by_principal_id,
        )
        self._grants[action_id] = grant

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectMembership):
            return NotImplemented
        return self.identity == other.identity

    @override
    def __hash__(self) -> int:
        return hash(self.identity)
