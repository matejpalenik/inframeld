"""Persist exact Project grant transitions and recover immutable original outcomes."""

import os
from dataclasses import replace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select, update
from tests.support.project_action_grant_postgres_scenarios import (
    change_project_grant,
    seed_project_grant_recipients,
)
from tests.support.project_membership_postgres_scenarios import change_membership

from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_operation_result_row import (
    ProjectActionGrantOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    IdempotencyKeyReusedError,
    StaleRevisionError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def test_assignment_level_change_noop_removal_and_regrant_preserve_history(
    database: Database,
) -> None:
    seed = await seed_project_grant_recipients(database)
    assigned = await change_project_grant(database, seed, revision=2, key="assign")
    assert (assigned.status_code, assigned.changed, assigned.access_revision) == (201, True, 3)
    grant_key = (seed.project.project_id.value, seed.bob_id.value, "inspect-budget")
    async with database.session() as session:
        grant = await session.get(ProjectActionGrantRow, grant_key)
        assert grant is not None
        original_time, original_actor = grant.assigned_at, grant.assigned_by_principal_id
    delegated = await change_project_grant(
        database, seed, revision=3, key="delegate", can_grant=True
    )
    noop = await change_project_grant(database, seed, revision=4, key="same-level", can_grant=True)
    assert (delegated.status_code, delegated.changed, delegated.access_revision) == (200, True, 4)
    assert (noop.status_code, noop.changed, noop.access_revision) == (200, False, 4)
    async with database.session() as session:
        grant = await session.get(ProjectActionGrantRow, grant_key)
        assert grant is not None and grant.can_grant
        assert (grant.assigned_at, grant.assigned_by_principal_id) == (
            original_time,
            original_actor,
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(
                    AccessAuditEventRow.correlation_id.in_(
                        (
                            assigned.operation.operation_id.value,
                            delegated.operation.operation_id.value,
                            noop.operation.operation_id.value,
                        )
                    )
                )
            )
            == 2
        )
    removed = await change_project_grant(database, seed, revision=4, key="remove", removing=True)
    absent = await change_project_grant(
        database, seed, revision=5, key="already-absent", removing=True
    )
    assert (removed.changed, removed.access_revision, absent.changed, absent.access_revision) == (
        True,
        5,
        False,
        5,
    )
    restored = await change_project_grant(database, seed, revision=5, key="fresh-assignment")
    assert restored.status_code == 201 and restored.access_revision == 6
    async with database.session() as session:
        grant = await session.get(ProjectActionGrantRow, grant_key)
        assert grant is not None and not grant.can_grant and grant.assigned_at > original_time
        receipts = (await session.scalars(select(ProjectActionGrantOperationResultRow))).all()
        assert len(receipts) == 6
        assert sum(row.changed for row in receipts) == 4
        assert await session.scalar(select(ProjectRow.access_revision)) == 6


async def test_original_set_and_remove_do_not_reapply_to_later_assignments(
    database: Database,
) -> None:
    seed = await seed_project_grant_recipients(database)
    original = await change_project_grant(database, seed, revision=2, key="original-set")
    removed = await change_project_grant(
        database, seed, revision=3, key="original-remove", removing=True
    )
    await change_project_grant(database, seed, revision=4, key="later-delegation", can_grant=True)
    replayed_set = await change_project_grant(database, seed, revision=2, key="original-set")
    replayed_remove = await change_project_grant(
        database, seed, revision=3, key="original-remove", removing=True
    )
    assert replace(replayed_set, operation=original.operation) == original
    assert replace(replayed_remove, operation=removed.operation) == removed
    assert not replayed_set.operation.created and not replayed_remove.operation.created
    assert replayed_set.operation.expires_at == original.operation.expires_at
    async with database.session() as session:
        grant = await session.get(
            ProjectActionGrantRow,
            (seed.project.project_id.value, seed.bob_id.value, "inspect-budget"),
        )
        assert grant is not None and grant.can_grant
        assert await session.scalar(select(ProjectRow.access_revision)) == 5


@pytest.mark.parametrize("case", ["stale", "key-content", "actor-use-only", "actor-suspended"])
async def test_fresh_conflicts_and_current_authority_precede_original_disclosure(
    database: Database, case: str
) -> None:
    seed = await seed_project_grant_recipients(database)
    original = await change_project_grant(database, seed, revision=2, key="original")
    async with database.session() as session, session.begin():
        if case == "actor-use-only":
            await session.execute(
                update(ProjectActionGrantRow)
                .where(
                    ProjectActionGrantRow.project_id == seed.project.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id
                    == seed.actor.access.actor_principal_id.value,
                    ProjectActionGrantRow.action == "inspect-budget",
                )
                .values(can_grant=False)
            )
        elif case == "actor-suspended":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.actor.access.actor_principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
    error = (
        StaleRevisionError
        if case == "stale"
        else IdempotencyKeyReusedError
        if case == "key-content"
        else AccessDeniedError
    )
    with pytest.raises(error):
        await change_project_grant(
            database,
            seed,
            revision=2,
            key="fresh" if case == "stale" else "original",
            can_grant=case == "key-content",
        )
    async with database.session() as session:
        assert await session.scalar(select(ProjectRow.access_revision)) == 3
        assert (
            await session.get(
                ProjectActionGrantOperationResultRow, original.operation.operation_id.value
            )
            is not None
        )


@pytest.mark.parametrize("case", ["suspended", "incoherent", "recovery", "departed"])
async def test_delete_and_original_replay_do_not_require_fresh_assignment_eligibility(
    database: Database, case: str
) -> None:
    seed = await seed_project_grant_recipients(database)
    original = await change_project_grant(database, seed, revision=2, key="original")
    revision = 3
    if case == "departed":
        await change_membership(database, seed, revision=3, key="depart-bob", remove=True)
        revision = 4
    else:
        async with database.session() as session, session.begin():
            if case == "suspended":
                await session.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == seed.bob_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
            elif case == "incoherent":
                history_id = "recipient-completed-recovery-history"
                session.add(
                    IdentityRecoveryAdmissionRow(
                        operation_id=history_id,
                        installation_id=seed.actor.binding.installation_id.value,
                        authority=seed.actor.binding.identity.authority.value,
                        subject=str(UUID(int=200)),
                        flow_id=uuid4(),
                        event_kind=IdentityRecoveryEventKind.PASSWORD_RESET,
                    )
                )
                await session.flush()
                # Qualify local state, without claiming provider cleanup evidence.
                await session.execute(
                    update(IdentityRecoveryAdmissionRow)
                    .where(IdentityRecoveryAdmissionRow.operation_id == history_id)
                    .values(
                        kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                        hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
                        released_at=func.now(),
                    )
                )
                await session.execute(
                    delete(HumanCredentialVersionRow).where(
                        HumanCredentialVersionRow.installation_id
                        == seed.actor.binding.installation_id.value,
                        HumanCredentialVersionRow.authority
                        == seed.actor.binding.identity.authority.value,
                        HumanCredentialVersionRow.subject == str(UUID(int=200)),
                    )
                )
            else:
                session.add(
                    IdentityRecoveryAdmissionRow(
                        operation_id="recipient-grant-recovery",
                        installation_id=seed.actor.binding.installation_id.value,
                        authority=seed.actor.binding.identity.authority.value,
                        subject=str(UUID(int=200)),
                        flow_id=uuid4(),
                        event_kind=IdentityRecoveryEventKind.PASSWORD_RESET,
                    )
                )
    replayed = await change_project_grant(database, seed, revision=2, key="original")
    assert replace(replayed, operation=original.operation) == original
    with pytest.raises(ConflictError):
        await change_project_grant(database, seed, revision=revision, key="fresh-ineligible")
    removed = await change_project_grant(
        database, seed, revision=revision, key="remove-ineligible", removing=True
    )
    assert removed.changed is (case != "departed")
    assert removed.access_revision == revision + int(removed.changed)


async def test_last_exact_grantor_cannot_remove_own_delegation(database: Database) -> None:
    seed = await seed_project_grant_recipients(database)
    with pytest.raises(ConflictError):
        await change_project_grant(
            database,
            seed,
            revision=2,
            key="strand",
            removing=True,
            recipient=seed.actor.access.actor_principal_id,
        )
    await change_project_grant(database, seed, revision=2, key="handover", can_grant=True)
    removed = await change_project_grant(
        database,
        seed,
        revision=3,
        key="depart-responsibility",
        removing=True,
        recipient=seed.actor.access.actor_principal_id,
    )
    assert removed.changed and removed.access_revision == 4
    with pytest.raises(AccessDeniedError):
        await change_project_grant(
            database,
            seed,
            revision=3,
            key="depart-responsibility",
            removing=True,
            recipient=seed.actor.access.actor_principal_id,
        )
    with pytest.raises(ConflictError):
        await change_project_grant(
            database,
            seed,
            revision=4,
            key="bob-strands",
            removing=True,
            recipient=seed.bob_id,
            access=seed.bob_access,
        )
