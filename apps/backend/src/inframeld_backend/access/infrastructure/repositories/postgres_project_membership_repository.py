from dataclasses import dataclass
from typing import final, override

from sqlalchemy import Nullable, and_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from inframeld_backend.access.application.dtos.project_use_only_grant_assigned_audit_event_dto import (
    ProjectUseOnlyGrantAssignedAuditEventDTO,
)
from inframeld_backend.access.application.protocols.audit_event_writer import AuditEventWriter
from inframeld_backend.access.application.protocols.project_membership_repository import (
    ProjectMembershipRepository,
)
from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class _GrantSnapshot:
    project_id: ProjectId
    principal_id: PrincipalId
    action_id: ActionId
    level: ProjectGrantLevel
    assigned_by_principal_id: PrincipalId | None


@dataclass(frozen=True, slots=True)
class _MembershipSnapshot:
    organization_id: OrganizationId
    project_id: ProjectId
    principal_id: PrincipalId
    principal_kind: PrincipalKind
    grants: tuple[_GrantSnapshot, ...]


@dataclass(slots=True)
class _TrackedMembership:
    membership: ProjectMembership
    snapshot: _MembershipSnapshot


def _snapshot(membership: ProjectMembership) -> _MembershipSnapshot:
    return _MembershipSnapshot(
        organization_id=membership.organization_id,
        project_id=membership.project_id,
        principal_id=membership.principal_id,
        principal_kind=membership.principal_kind,
        grants=tuple(
            _GrantSnapshot(
                project_id=grant.project_id,
                principal_id=grant.recipient_principal_id,
                action_id=grant.action_id,
                level=grant.level,
                assigned_by_principal_id=grant.assigned_by_principal_id,
            )
            for grant in membership.grants
        ),
    )


def _additions(
    original: _MembershipSnapshot, current: _MembershipSnapshot
) -> tuple[_GrantSnapshot, ...]:
    if (
        original.organization_id != current.organization_id
        or original.project_id != current.project_id
        or original.principal_id != current.principal_id
        or original.principal_kind is not current.principal_kind
    ):
        raise RuntimeError("Membership metadata cannot be modified.")

    before = {grant.action_id: grant for grant in original.grants}
    after = {grant.action_id: grant for grant in current.grants}
    if len(after) != len(current.grants):
        raise RuntimeError("Duplicate action additions are not supported.")
    if any(after.get(action) != grant for action, grant in before.items()):
        raise RuntimeError("Existing grants cannot be modified or removed.")
    added = tuple(grant for grant in current.grants if grant.action_id not in before)
    for grant in added:
        if (
            grant.project_id != current.project_id
            or grant.principal_id != current.principal_id
            or grant.level is not ProjectGrantLevel.USE_ONLY
            or grant.assigned_by_principal_id is None
        ):
            raise RuntimeError(
                "Only attributed use-only additions in this membership are supported."
            )
    return added


@final
class PostgresProjectMembershipRepository(ProjectMembershipRepository):
    """Track loaded aggregates and immutable value snapshots on one session transaction.

    Load with one outer join. Save additions using the project's conditional
    revision update, conflict-safe inserts and the injected session-bound audit
    writer. Keep database-generated timestamps on their existing rows.
    """

    def __init__(self, session: AsyncSession, audit_events: AuditEventWriter) -> None:
        self._session = session
        self._audit_events = audit_events
        self._transaction: AsyncSessionTransaction | None = None
        self._failed = False
        self._tracked: dict[tuple[OrganizationId, ProjectId, PrincipalId], _TrackedMembership] = {}

    def _require_transaction(self) -> None:
        if self._failed:
            raise RuntimeError("This repository cannot be reused after a failed save.")
        transaction = self._session.get_nested_transaction() or self._session.get_transaction()
        if transaction is None or not transaction.is_active:
            raise RuntimeError("An active transaction is required for membership persistence.")
        if self._transaction is None:
            self._transaction = transaction
        elif transaction is not self._transaction:
            raise RuntimeError("This repository belongs to another transaction.")

    @override
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId, principal_id: PrincipalId
    ) -> ProjectMembership:
        self._require_transaction()
        key = (organization_id, project_id, principal_id)
        tracked = self._tracked.get(key)
        if tracked is not None:
            return tracked.membership

        statement = (
            select(ProjectMembershipRow, Nullable(ProjectActionGrantRow))
            .outerjoin(
                ProjectActionGrantRow,
                and_(
                    ProjectActionGrantRow.project_id == ProjectMembershipRow.project_id,
                    ProjectActionGrantRow.recipient_principal_id
                    == ProjectMembershipRow.principal_id,
                ),
            )
            .where(
                ProjectMembershipRow.organization_id == organization_id.value,
                ProjectMembershipRow.project_id == project_id.value,
                ProjectMembershipRow.principal_id == principal_id.value,
            )
            .order_by(ProjectActionGrantRow.action)
        )
        rows = (await self._session.execute(statement)).all()
        if not rows:
            raise ResourceNotFoundError()
        member = rows[0][0]
        grants: list[ProjectActionGrant] = []
        for _, grant in rows:
            if grant is None:
                continue
            if (
                grant.project_id != member.project_id
                or grant.recipient_principal_id != member.principal_id
                or grant.recipient_kind is not member.principal_kind
            ):
                raise RuntimeError("Stored grants do not match their membership.")
            grants.append(
                ProjectActionGrant(
                    project_id=ProjectId(grant.project_id),
                    recipient_principal_id=PrincipalId(grant.recipient_principal_id),
                    action_id=ActionId(grant.action),
                    level=ProjectGrantLevel.USE_AND_GRANT
                    if grant.can_grant
                    else ProjectGrantLevel.USE_ONLY,
                    assigned_by_principal_id=(
                        PrincipalId(grant.assigned_by_principal_id)
                        if grant.assigned_by_principal_id is not None
                        else None
                    ),
                )
            )
        membership = ProjectMembership(
            organization_id=OrganizationId(member.organization_id),
            project_id=ProjectId(member.project_id),
            principal_id=PrincipalId(member.principal_id),
            principal_kind=member.principal_kind,
            grants=tuple(grants),
        )
        self._tracked[key] = _TrackedMembership(membership, _snapshot(membership))
        return membership

    @override
    async def save(
        self,
        membership: ProjectMembership,
        *,
        expected_project_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        try:
            self._require_transaction()
            key = (membership.organization_id, membership.project_id, membership.principal_id)
            tracked = self._tracked.get(key)
            if tracked is None or tracked.membership is not membership:
                raise RuntimeError("Save only the membership instance loaded by this repository.")
            current = _snapshot(membership)
            additions = _additions(tracked.snapshot, current)
            if not additions:
                return
            await self._advance_revision(current, expected_project_access_revision)
            for grant in additions:
                await self._insert_grant(current, grant, operation_id)
            tracked.snapshot = current
        except BaseException:
            # Cancellation also invalidates snapshots. The transaction owner rolls back.
            self._failed = True
            raise

    async def _advance_revision(
        self, membership: _MembershipSnapshot, expected_revision: int
    ) -> None:
        statement = (
            update(ProjectRow)
            .where(
                ProjectRow.id == membership.project_id.value,
                ProjectRow.organization_id == membership.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
                ProjectRow.access_revision == expected_revision,
            )
            .values(access_revision=ProjectRow.access_revision + 1)
            .returning(ProjectRow.id)
        )
        if (await self._session.execute(statement)).scalar_one_or_none() is None:
            raise ConflictError("The project access revision has changed.")

    async def _insert_grant(
        self, membership: _MembershipSnapshot, grant: _GrantSnapshot, operation_id: OperationId
    ) -> None:
        actor = grant.assigned_by_principal_id
        if actor is None:
            raise RuntimeError("An assigning principal is required for a new grant.")
        statement = (
            insert(ProjectActionGrantRow)
            .values(
                project_id=grant.project_id.value,
                recipient_principal_id=grant.principal_id.value,
                recipient_kind=membership.principal_kind,
                action=grant.action_id.value,
                can_grant=grant.level is ProjectGrantLevel.USE_AND_GRANT,
                assigned_by_principal_id=actor.value,
            )
            .on_conflict_do_nothing(constraint="pk_project_action_grants")
            .returning(ProjectActionGrantRow.project_id)
        )
        if (await self._session.execute(statement)).scalar_one_or_none() is None:
            raise ConflictError("This project action grant already exists.")
        await self._audit_events.append(
            ProjectUseOnlyGrantAssignedAuditEventDTO(
                organization_id=membership.organization_id,
                project_id=membership.project_id,
                actor_principal_id=actor,
                recipient_principal_id=membership.principal_id,
                action_id=grant.action_id,
                operation_id=operation_id,
            )
        )
