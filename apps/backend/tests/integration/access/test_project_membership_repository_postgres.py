"""Exercise membership persistence independently of request authorization."""

import os
from dataclasses import replace
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.access_scenarios import MockAccessScenarios, ProjectAuthorizationSeedDTO

from inframeld_backend.access.application.dtos.project_use_only_grant_assigned_audit_event_dto import (
    ProjectUseOnlyGrantAssignedAuditEventDTO,
)
from inframeld_backend.access.application.protocols.audit_event_writer import AuditEventWriter
from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.repositories.postgres_project_membership_repository import (
    PostgresProjectMembershipRepository,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)

ACTION = ActionId("create-access-groups")
OPERATION = OperationId("membership-assignment")


async def seed_membership(
    database: Database, *, kind: PrincipalKind = PrincipalKind.HUMAN, existing: bool = False
) -> ProjectAuthorizationSeedDTO:
    async with database.session() as session, session.begin():
        return await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=existing, principal_kind=kind
        )


def repository(session: AsyncSession) -> PostgresProjectMembershipRepository:
    return PostgresProjectMembershipRepository(session, PostgresAuditEventWriter(session))


async def load(
    repo: PostgresProjectMembershipRepository, seed: ProjectAuthorizationSeedDTO
) -> ProjectMembership:
    return await repo.get(
        organization_id=seed.organization_id,
        project_id=seed.project_id,
        principal_id=seed.principal_id,
    )


async def assert_effects(
    database: Database,
    seed: ProjectAuthorizationSeedDTO,
    *,
    revision: int,
    grants: int,
    audits: int,
) -> None:
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == seed.project_id.value)
            )
            == revision
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(ProjectActionGrantRow.project_id == seed.project_id.value)
            )
            == grants
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.project_id == seed.project_id.value)
            )
            == audits
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [PrincipalKind.HUMAN, PrincipalKind.APPLICATION])
async def test_loads_empty_existing_membership(database: Database, kind: PrincipalKind) -> None:
    seed = await seed_membership(database, kind=kind)
    async with database.session() as session, session.begin():
        membership = await load(repository(session), seed)
        assert membership.organization_id == seed.organization_id
        assert membership.project_id == seed.project_id
        assert membership.principal_id == seed.principal_id
        assert membership.principal_kind is kind
        assert membership.grants == ()


@pytest.mark.asyncio
async def test_loads_complete_collection_with_levels_and_historical_attribution(
    database: Database,
) -> None:
    """Reconstitution includes use and delegation grants, even legacy unattributed ones."""
    seed = await seed_membership(database, existing=True)
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=seed.project_id.value,
                recipient_principal_id=seed.principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ACTION.value,
                can_grant=True,
                assigned_by_principal_id=seed.principal_id.value,
            )
        )
    async with database.session() as session, session.begin():
        membership = await load(repository(session), seed)
        grants = {grant.action_id: grant for grant in membership.grants}
        assert set(grants) == {seed.action, ACTION}
        assert grants[seed.action].level is ProjectGrantLevel.USE_ONLY
        assert grants[seed.action].assigned_by_principal_id is None
        assert grants[ACTION].level is ProjectGrantLevel.USE_AND_GRANT
        assert grants[ACTION].assigned_by_principal_id == seed.principal_id
        assert all(
            g.project_id == seed.project_id and g.recipient_principal_id == seed.principal_id
            for g in membership.grants
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["organization", "project", "principal"])
async def test_missing_scoped_membership_never_provisions(database: Database, missing: str) -> None:
    seed = await seed_membership(database)
    requested = replace(
        seed,
        organization_id=OrganizationId(uuid4())
        if missing == "organization"
        else seed.organization_id,
        project_id=ProjectId(uuid4()) if missing == "project" else seed.project_id,
        principal_id=PrincipalId(uuid4()) if missing == "principal" else seed.principal_id,
    )
    async with database.session() as session, session.begin():
        repo = repository(session)
        await load(repo, seed)
        with pytest.raises(ResourceNotFoundError):
            await load(repo, requested)
    await assert_effects(database, seed, revision=0, grants=0, audits=0)


@pytest.mark.asyncio
async def test_repeated_load_and_unchanged_save_do_not_write(database: Database) -> None:
    seed = await seed_membership(database, existing=True)
    async with database.session() as session, session.begin():
        repo = repository(session)
        membership = await load(repo, seed)
        assert await load(repo, seed) is membership
        await repo.save(membership, expected_project_access_revision=0, operation_id=OPERATION)
        await repo.save(membership, expected_project_access_revision=0, operation_id=OPERATION)
    await assert_effects(database, seed, revision=0, grants=1, audits=0)


@pytest.mark.asyncio
async def test_additions_preserve_existing_rows_and_repeated_save_is_unchanged(
    database: Database,
) -> None:
    """Saving a new action preserves legacy attribution and its database timestamp."""
    seed = await seed_membership(database, existing=True)
    async with database.session() as session:
        before = (
            await session.execute(
                select(
                    ProjectActionGrantRow.can_grant,
                    ProjectActionGrantRow.assigned_by_principal_id,
                    ProjectActionGrantRow.assigned_at,
                ).where(ProjectActionGrantRow.project_id == seed.project_id.value)
            )
        ).one()
    async with database.session() as session, session.begin():
        repo = repository(session)
        membership = await load(repo, seed)
        membership.assign_use_only_grant(
            action_id=ACTION, assigned_by_principal_id=seed.principal_id
        )
        await repo.save(membership, expected_project_access_revision=0, operation_id=OPERATION)
        assert await load(repo, seed) is membership
        await repo.save(membership, expected_project_access_revision=1, operation_id=OPERATION)
    await assert_effects(database, seed, revision=1, grants=2, audits=1)
    async with database.session() as session:
        after = (
            await session.execute(
                select(
                    ProjectActionGrantRow.can_grant,
                    ProjectActionGrantRow.assigned_by_principal_id,
                    ProjectActionGrantRow.assigned_at,
                ).where(
                    ProjectActionGrantRow.project_id == seed.project_id.value,
                    ProjectActionGrantRow.action == seed.action.value,
                )
            )
        ).one()
        assert after == before
        added = (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == seed.project_id.value,
                    ProjectActionGrantRow.action == ACTION.value,
                )
            )
        ).one()
        assert added.can_grant is False
        assert added.assigned_by_principal_id == seed.principal_id.value
        assert added.assigned_at is not None
        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.project_id == seed.project_id.value
                )
            )
        ).one()
        assert audit.correlation_id == OPERATION.value
        assert audit.actor_principal_id == seed.principal_id.value
        assert audit.affected_principal_id == seed.principal_id.value
        assert audit.action == ACTION.value
        assert audit.after_values == {"can_grant": False}


@pytest.mark.asyncio
async def test_multiple_additions_advance_project_revision_once(database: Database) -> None:
    seed = await seed_membership(database)
    async with database.session() as session, session.begin():
        repo = repository(session)
        membership = await load(repo, seed)
        for action in (ACTION, seed.action):
            membership.assign_use_only_grant(
                action_id=action, assigned_by_principal_id=seed.principal_id
            )
        await repo.save(membership, expected_project_access_revision=0, operation_id=OPERATION)
    await assert_effects(database, seed, revision=1, grants=2, audits=2)


@pytest.mark.asyncio
async def test_requires_transaction_without_autobegin(database: Database) -> None:
    seed = await seed_membership(database)
    async with database.session() as session:
        repo = repository(session)
        with pytest.raises(RuntimeError, match="active transaction"):
            await load(repo, seed)
        assert not session.in_transaction()


@pytest.mark.asyncio
@pytest.mark.parametrize("rolled_back", [False, True], ids=["commit", "rollback"])
async def test_repository_cannot_cross_transaction_boundary(
    database: Database, rolled_back: bool
) -> None:
    seed = await seed_membership(database)
    async with database.session() as session:
        repo = repository(session)
        async with session.begin() as transaction:
            membership = await load(repo, seed)
            if rolled_back:
                await transaction.rollback()
        with pytest.raises(RuntimeError, match="active transaction"):
            await load(repo, seed)
        async with session.begin():
            with pytest.raises(RuntimeError, match="transaction"):
                await load(repo, seed)
            with pytest.raises(RuntimeError):
                await repo.save(
                    membership, expected_project_access_revision=0, operation_id=OPERATION
                )
    await assert_effects(database, seed, revision=0, grants=0, audits=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["clone", "another-repository"])
async def test_save_requires_exact_instance_loaded_by_this_repository(
    database: Database, source: str
) -> None:
    seed = await seed_membership(database)
    async with database.session() as session, session.begin():
        repo = repository(session)
        loaded = await load(repo, seed)
        supplied = (
            await load(repository(session), seed)
            if source == "another-repository"
            else ProjectMembership(
                organization_id=loaded.organization_id,
                project_id=loaded.project_id,
                principal_id=loaded.principal_id,
                principal_kind=loaded.principal_kind,
                grants=loaded.grants,
            )
        )
        assert supplied == loaded and supplied is not loaded
        supplied.assign_use_only_grant(action_id=ACTION, assigned_by_principal_id=seed.principal_id)
        with pytest.raises(RuntimeError, match="loaded"):
            await repo.save(supplied, expected_project_access_revision=0, operation_id=OPERATION)
    await assert_effects(database, seed, revision=0, grants=0, audits=0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change", ["level", "attribution", "removal", "delegation-addition", "unattributed-addition"]
)
async def test_unsupported_delta_is_rejected_without_writes(
    database: Database, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    """Fault injection checks values explicitly, even when child identity stays equal."""
    seed = await seed_membership(database, existing=True)
    async with database.session() as session, session.begin():
        repo = repository(session)
        membership = await load(repo, seed)
        original = membership.grants[0]
        if change == "removal":
            altered: tuple[ProjectActionGrant, ...] = ()
        elif change in ("level", "attribution"):
            changed = (
                replace(original, level=ProjectGrantLevel.USE_AND_GRANT)
                if change == "level"
                else replace(original, assigned_by_principal_id=seed.principal_id)
            )
            assert changed == original
            altered = (changed,)
        else:
            altered = (
                original,
                ProjectActionGrant(
                    project_id=seed.project_id,
                    recipient_principal_id=seed.principal_id,
                    action_id=ACTION,
                    level=ProjectGrantLevel.USE_AND_GRANT
                    if change == "delegation-addition"
                    else ProjectGrantLevel.USE_ONLY,
                    assigned_by_principal_id=seed.principal_id
                    if change == "delegation-addition"
                    else None,
                ),
            )
        with monkeypatch.context() as patch:
            patch.setattr(ProjectMembership, "grants", property(lambda _: altered))
            with pytest.raises(RuntimeError, match="supported|modified|removed|use-only"):
                await repo.save(
                    membership, expected_project_access_revision=0, operation_id=OPERATION
                )
    await assert_effects(database, seed, revision=0, grants=1, audits=0)


@pytest.mark.asyncio
@pytest.mark.parametrize("inactive", [False, True], ids=["stale-revision", "inactive-project"])
async def test_conditional_project_update_rejects_changed_state(
    database: Database, inactive: bool
) -> None:
    seed = await seed_membership(database)
    if inactive:
        async with database.session() as session, session.begin():
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == seed.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )
    with pytest.raises(ConflictError, match="revision"):
        async with database.session() as session, session.begin():
            repo = repository(session)
            membership = await load(repo, seed)
            membership.assign_use_only_grant(
                action_id=ACTION, assigned_by_principal_id=seed.principal_id
            )
            await repo.save(
                membership,
                expected_project_access_revision=0 if inactive else 9,
                operation_id=OPERATION,
            )
    await assert_effects(database, seed, revision=0, grants=0, audits=0)


@pytest.mark.asyncio
async def test_database_duplicate_guard_rolls_back_revision(database: Database) -> None:
    """A row added after loading cannot be overwritten by the cached aggregate."""
    seed = await seed_membership(database)
    with pytest.raises(ConflictError, match="already exists"):
        async with database.session() as session, session.begin():
            repo = repository(session)
            membership = await load(repo, seed)
            membership.assign_use_only_grant(
                action_id=ACTION, assigned_by_principal_id=seed.principal_id
            )
            session.add(
                ProjectActionGrantRow(
                    project_id=seed.project_id.value,
                    recipient_principal_id=seed.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=ACTION.value,
                    can_grant=True,
                )
            )
            await session.flush()
            await repo.save(membership, expected_project_access_revision=0, operation_id=OPERATION)
    await assert_effects(database, seed, revision=0, grants=0, audits=0)


class MockFailingAuditEventWriter(AuditEventWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._real = PostgresAuditEventWriter(session)

    @override
    async def append(self, event: ProjectUseOnlyGrantAssignedAuditEventDTO) -> None:
        await self._real.append(event)
        raise RuntimeError("Injected audit failure")


@pytest.mark.asyncio
async def test_failed_save_invalidates_repository_and_owner_rolls_back(database: Database) -> None:
    seed = await seed_membership(database)
    with pytest.raises(RuntimeError, match="Injected audit failure"):
        async with database.session() as session, session.begin():
            repo = PostgresProjectMembershipRepository(
                session, MockFailingAuditEventWriter(session)
            )
            membership = await load(repo, seed)
            membership.assign_use_only_grant(
                action_id=ACTION, assigned_by_principal_id=seed.principal_id
            )
            try:
                await repo.save(
                    membership, expected_project_access_revision=0, operation_id=OPERATION
                )
            except RuntimeError:
                assert session.in_transaction()
                assert (
                    await session.scalar(
                        select(ProjectRow.access_revision).where(
                            ProjectRow.id == seed.project_id.value
                        )
                    )
                    == 1
                )
                with pytest.raises(RuntimeError, match="failed"):
                    await load(repo, seed)
                with pytest.raises(RuntimeError, match="failed"):
                    await repo.save(
                        membership, expected_project_access_revision=1, operation_id=OPERATION
                    )
                raise
    await assert_effects(database, seed, revision=0, grants=0, audits=0)
