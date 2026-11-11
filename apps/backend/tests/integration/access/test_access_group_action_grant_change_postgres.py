"""Qualify exact access group grant persistence, current authority and replay."""

import os
from dataclasses import replace

import pytest
from sqlalchemy import event, func, select, update
from sqlalchemy.orm import Session
from tests.support.access_group_scenarios import create_group, delete_group
from tests.support.application_account_scenarios import create_account
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.remove_access_group_action_grant_command import (
    RemoveAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_access_group_action_grant_command import (
    SetAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_action_grant_change_result_dto import (
    AccessGroupActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_operation_result_row import (
    GroupActionGrantOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.access_group_grant_composition import (
    open_access_group_grant_change,
)
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL services",
    ),
]


def _fingerprints() -> RequestFingerprintService:
    return RequestFingerprintService(RequestFingerprintKey(b"K" * 32))


async def _seed(database: Database) -> tuple[MembershipProjectSeedDTO, CreatedAccessGroupDTO]:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join-bob-before-grants")
    created = await create_group(database, seed.actor.access, seed.project.project_id, revision=2)
    return seed, created.group


async def _revision(database: Database, project: ProjectId) -> int:
    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == project.value)
        )
        assert revision is not None
        return revision


def _context(
    project: ProjectId,
    target: AccessGroupId,
    recipient: PrincipalId,
    action: str,
    key: str,
    method: HttpMethod = HttpMethod.PUT,
) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        method=method,
        requested_route=f"/v1/projects/{project.value}/access-groups/{target.value}/grants/{recipient.value}/{action}",
        key=IdempotencyKey(key),
    )


async def _set(
    database: Database,
    seed: MembershipProjectSeedDTO,
    target: AccessGroupId,
    *,
    action: str,
    recipient: PrincipalId,
    level: bool,
    revision: int,
    key: str,
    access: AccessContextDTO | None = None,
) -> AccessGroupActionGrantChangeResultDTO:
    async with open_access_group_grant_change(database, _fingerprints()) as service:
        return await service.set_grant(
            access=access or seed.actor.access,
            command=SetAccessGroupActionGrantCommand(
                project_id=seed.project.project_id,
                group_id=target,
                recipient_principal_id=recipient,
                action_id=ActionId(action),
                can_grant=level,
                expected_access_revision=revision,
            ),
            context=_context(seed.project.project_id, target, recipient, action, key),
        )


async def _remove(
    database: Database,
    seed: MembershipProjectSeedDTO,
    target: AccessGroupId,
    *,
    action: str,
    recipient: PrincipalId,
    revision: int,
    key: str,
    access: AccessContextDTO | None = None,
) -> AccessGroupActionGrantChangeResultDTO:
    async with open_access_group_grant_change(database, _fingerprints()) as service:
        return await service.remove_grant(
            access=access or seed.actor.access,
            command=RemoveAccessGroupActionGrantCommand(
                project_id=seed.project.project_id,
                group_id=target,
                recipient_principal_id=recipient,
                action_id=ActionId(action),
                expected_access_revision=revision,
            ),
            context=_context(
                seed.project.project_id, target, recipient, action, key, HttpMethod.DELETE
            ),
        )


@pytest.mark.parametrize("action", ["add-documents", "update-documents", "delete-documents"])
@pytest.mark.parametrize("level", [False, True])
async def test_exact_assignment_noop_change_remove_regrant_and_old_removal_replay(
    database: Database, action: str, level: bool
) -> None:
    seed, created = await _seed(database)
    target = created.group_id
    revision = await _revision(database, seed.project.project_id)
    first = await _set(
        database,
        seed,
        target,
        action=action,
        recipient=seed.bob_id,
        level=level,
        revision=revision,
        key="first",
    )
    assert (first.status_code, first.changed, first.access_revision) == (201, True, revision + 1)
    noop = await _set(
        database,
        seed,
        target,
        action=action,
        recipient=seed.bob_id,
        level=level,
        revision=revision + 1,
        key="noop",
    )
    assert (noop.status_code, noop.changed, noop.access_revision) == (200, False, revision + 1)
    changed = await _set(
        database,
        seed,
        target,
        action=action,
        recipient=seed.bob_id,
        level=not level,
        revision=revision + 1,
        key="change-level",
    )
    assert changed.changed and changed.access_revision == revision + 2
    removed = await _remove(
        database,
        seed,
        target,
        action=action,
        recipient=seed.bob_id,
        revision=revision + 2,
        key="remove-original",
    )
    assert removed.changed and removed.can_grant is None and removed.access_revision == revision + 3
    await _set(
        database,
        seed,
        target,
        action=action,
        recipient=seed.bob_id,
        level=level,
        revision=revision + 3,
        key="regrant",
    )
    replay = await _remove(
        database,
        seed,
        target,
        action=action,
        recipient=seed.bob_id,
        revision=revision + 2,
        key="remove-original",
    )
    _assert_original_replay(replay, removed)
    assert await _revision(database, seed.project.project_id) == revision + 4
    async with database.session() as session:
        stored = await session.get(
            GroupActionGrantRow,
            (seed.project.project_id.value, target.value, seed.bob_id.value, action),
        )
        assert stored is not None and stored.can_grant is level
        assert (
            await session.scalar(
                select(func.count()).select_from(GroupActionGrantOperationResultRow)
            )
            == 5
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type.like("group_action_grant_%"))
            )
            == 4
        )
        receipt = await session.get(
            GroupActionGrantOperationResultRow, first.operation.operation_id.value
        )
        native = await session.get(IdempotencyReservationRow, first.operation.operation_id.value)
        assert (
            receipt is not None
            and receipt.project_id == seed.project.project_id.value
            and receipt.group_id == target.value
        )
        assert native is not None and native.state is OperationReservationState.REPLAYABLE
        assert native.lookup_authority_family == "access_group_grant_read"
        assert native.expires_at == first.operation.expires_at


async def test_required_audit_failure_rolls_back_grant_revision_reservation_and_original_result(
    database: Database,
) -> None:
    seed, created = await _seed(database)
    target = created.group_id
    revision = await _revision(database, seed.project.project_id)

    def reject_audit(session: Session, flush_context: object, instances: object) -> None:
        if any(
            isinstance(row, AccessAuditEventRow)
            and row.event_type.startswith("group_action_grant_")
            for row in session.new
        ):
            raise RuntimeError("controlled grant audit failure")

    event.listen(Session, "before_flush", reject_audit)
    try:
        with pytest.raises(RuntimeError, match="controlled grant audit failure"):
            await _set(
                database,
                seed,
                target,
                action="add-documents",
                recipient=seed.bob_id,
                level=False,
                revision=revision,
                key="audit-rollback",
            )
    finally:
        event.remove(Session, "before_flush", reject_audit)
    assert await _revision(database, seed.project.project_id) == revision
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count()).select_from(GroupActionGrantOperationResultRow)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key == "audit-rollback")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupActionGrantRow)
                .where(GroupActionGrantRow.recipient_principal_id == seed.bob_id.value)
            )
            == 0
        )


async def test_removal_allows_a_suspended_scoped_recipient_without_restoring_it_on_replay(
    database: Database,
) -> None:
    seed, created = await _seed(database)
    target = created.group_id
    revision = await _revision(database, seed.project.project_id)
    first = await _set(
        database,
        seed,
        target,
        action="add-documents",
        recipient=seed.bob_id,
        level=False,
        revision=revision,
        key="before-suspend",
    )
    async with database.session() as session, session.begin():
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == seed.actor.organization_id.value)
            .with_for_update()
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == seed.bob_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    replay = await _set(
        database,
        seed,
        target,
        action="add-documents",
        recipient=seed.bob_id,
        level=False,
        revision=revision,
        key="before-suspend",
    )
    _assert_original_replay(replay, first)
    removed = await _remove(
        database,
        seed,
        target,
        action="add-documents",
        recipient=seed.bob_id,
        revision=revision + 1,
        key="remove-suspended",
    )
    assert removed.changed and removed.can_grant is None
    with pytest.raises(ConflictError):
        await _set(
            database,
            seed,
            target,
            action="add-documents",
            recipient=seed.bob_id,
            level=False,
            revision=revision + 2,
            key="cannot-regrant-suspended",
        )


async def test_manager_write_replay_differs_from_exact_delegation_required_for_generic_lookup(
    database: Database,
) -> None:
    seed, group = await _seed(database)
    target, alice = group.group_id, seed.actor.access.actor_principal_id
    revision = await _revision(database, seed.project.project_id)
    original = await _set(
        database,
        seed,
        target,
        action="add-documents",
        recipient=seed.bob_id,
        level=False,
        revision=revision,
        key="manager-original",
    )
    async with database.session() as session:
        installed = await session.scalar(select(InstallationIdentityRow.installation_id))
        assert installed is not None
    query = LookupOriginalOperationQuery(
        installation_id=InstallationId(installed),
        organization_id=seed.actor.organization_id,
        project_id=seed.project.project_id,
        method=HttpMethod.PUT,
        requested_route=_context(
            seed.project.project_id, target, seed.bob_id, "add-documents", "manager-original"
        ).requested_route,
        key=IdempotencyKey("manager-original"),
        expected_authority=OperationLookupAuthority(
            family=OperationLookupAuthorityFamily.ACCESS_GROUP_GRANT_READ,
            action_id=ActionId("add-documents"),
        ),
    )
    async with open_original_operation_lookup(database) as lookup:
        with pytest.raises(AccessDeniedError):
            await lookup.lookup(access=seed.actor.access, query=query)
    await _set(
        database,
        seed,
        target,
        action="add-documents",
        recipient=alice,
        level=True,
        revision=revision + 1,
        key="self-delegation",
    )
    async with open_original_operation_lookup(database) as lookup:
        found = await lookup.lookup(access=seed.actor.access, query=query)
    assert (
        isinstance(found, CompletedSynchronousOperationDTO)
        and found.operation_id == original.operation.operation_id
    )
    # Alice's ordinary membership and management survive removing her direct grant.
    await _remove(
        database,
        seed,
        target,
        action="add-documents",
        recipient=alice,
        revision=revision + 2,
        key="remove-self-direct",
    )
    replay = await _set(
        database,
        seed,
        target,
        action="add-documents",
        recipient=seed.bob_id,
        level=False,
        revision=revision,
        key="manager-original",
    )
    _assert_original_replay(replay, original)
    async with open_original_operation_lookup(database) as lookup:
        with pytest.raises(AccessDeniedError):
            await lookup.lookup(access=seed.actor.access, query=query)


async def test_no_eligible_manager_can_substitute_for_removing_the_last_current_delegate(
    database: Database,
) -> None:
    seed, group = await _seed(database)
    revision = await _revision(database, seed.project.project_id)
    await _set(
        database,
        seed,
        group.group_id,
        action="add-documents",
        recipient=seed.bob_id,
        level=True,
        revision=revision,
        key="delegate-bob-last",
    )
    async with database.session() as session, session.begin():
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == seed.actor.organization_id.value)
            .with_for_update()
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == seed.actor.access.actor_principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    with pytest.raises(ConflictError):
        await _remove(
            database,
            seed,
            group.group_id,
            action="add-documents",
            recipient=seed.bob_id,
            revision=revision + 1,
            key="remove-last-with-ineligible-manager",
            access=seed.bob_access,
        )
    assert await _revision(database, seed.project.project_id) == revision + 1


async def test_bound_application_receives_use_only_and_can_be_removed_when_inactive(
    database: Database,
) -> None:
    seed, group = await _seed(database)
    revision = await _revision(database, seed.project.project_id)
    account = (
        await create_account(
            database, seed.actor.access, seed.project.project_id, revision=revision
        )
    ).account
    assigned = await _set(
        database,
        seed,
        group.group_id,
        action="add-documents",
        recipient=account.principal_id,
        level=False,
        revision=revision + 1,
        key="application-use",
    )
    assert assigned.can_grant is False
    with pytest.raises(InvalidInputError):
        await _set(
            database,
            seed,
            group.group_id,
            action="add-documents",
            recipient=account.principal_id,
            level=True,
            revision=revision + 2,
            key="application-cannot-delegate",
        )
    async with database.session() as session, session.begin():
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == seed.actor.organization_id.value)
            .with_for_update()
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == account.principal_id.value)
            .values(status=PrincipalStatus.RETIRED)
        )
    removed = await _remove(
        database,
        seed,
        group.group_id,
        action="add-documents",
        recipient=account.principal_id,
        revision=revision + 2,
        key="remove-inactive-application",
    )
    assert removed.changed and removed.can_grant is None


async def test_group_deletion_preserves_immutable_results_but_never_authorizes_replay(
    database: Database,
) -> None:
    seed, group = await _seed(database)
    revision = await _revision(database, seed.project.project_id)
    original = await _set(
        database,
        seed,
        group.group_id,
        action="add-documents",
        recipient=seed.bob_id,
        level=False,
        revision=revision,
        key="before-group-deletion",
    )
    await _remove(
        database,
        seed,
        group.group_id,
        action="add-documents",
        recipient=seed.bob_id,
        revision=revision + 1,
        key="clear-group-grant",
    )
    await delete_group(
        database,
        seed.actor.access,
        group,
        revision=revision + 2,
        key="delete-unused-group-after-grant",
    )
    async with database.session() as session:
        assert await session.get(AccessGroupRow, group.group_id.value) is None
        retained = await session.get(
            GroupActionGrantOperationResultRow, original.operation.operation_id.value
        )
        assert retained is not None and retained.group_id == group.group_id.value
    with pytest.raises(ResourceNotFoundError):
        await _set(
            database,
            seed,
            group.group_id,
            action="add-documents",
            recipient=seed.bob_id,
            level=False,
            revision=revision,
            key="before-group-deletion",
        )


def _assert_original_replay(
    replay: AccessGroupActionGrantChangeResultDTO, original: AccessGroupActionGrantChangeResultDTO
) -> None:
    """Distinguish admission while retaining every original business and correlation field."""
    assert original.operation.created is True and replay.operation.created is False
    assert replay.operation.operation_id == original.operation.operation_id
    assert replay.operation.expires_at == original.operation.expires_at
    assert replay.operation.replay_kind is original.operation.replay_kind
    assert replace(replay, operation=original.operation) == original


async def test_departed_human_fresh_delete_records_absence_without_rejoin(
    database: Database,
) -> None:
    seed, created = await _seed(database)
    target = created.group_id
    revision = await _revision(database, seed.project.project_id)
    await _set(
        database,
        seed,
        target,
        action="add-documents",
        recipient=seed.bob_id,
        level=False,
        revision=revision,
        key="before-departure",
    )
    departed = await change_membership(
        database, seed, revision=revision + 1, key="delivered-bob-departure", remove=True
    )
    assert departed.changed
    reviewed = await _revision(database, seed.project.project_id)
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is None
        )
        assert (
            await session.get(
                GroupActionGrantRow,
                (seed.project.project_id.value, target.value, seed.bob_id.value, "add-documents"),
            )
            is None
        )
    # This is a new DELETE identity after delivered departure, not old-write replay.
    result = await _remove(
        database,
        seed,
        target,
        action="add-documents",
        recipient=seed.bob_id,
        revision=reviewed,
        key="fresh-delete-after-departure",
    )
    assert result.status_code == 200 and result.changed is False and result.can_grant is None
    assert result.access_revision == reviewed == departed.access_revision
    replay = await _remove(
        database,
        seed,
        target,
        action="add-documents",
        recipient=seed.bob_id,
        revision=reviewed,
        key="fresh-delete-after-departure",
    )
    _assert_original_replay(replay, result)
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is None
        )
        assert (
            await session.get(
                GroupActionGrantRow,
                (seed.project.project_id.value, target.value, seed.bob_id.value, "add-documents"),
            )
            is None
        )
        receipt = await session.get(
            GroupActionGrantOperationResultRow, result.operation.operation_id.value
        )
        assert (
            receipt is not None
            and receipt.before_can_grant is None
            and receipt.can_grant is None
            and not receipt.changed
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.correlation_id == result.operation.operation_id.value)
            )
            == 0
        )
