"""Qualify current issuance observations against real account and credential rows."""

import asyncio
import os
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import DateTime, Integer, String, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.access_group_scenarios import change_group, create_group
from tests.support.application_account_scenarios import create_account
from tests.support.application_key_scenarios import seed_application_key, store_application_key
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.dtos.application_key_issuance_facts_dto import (
    ApplicationKeyIssuanceFactsDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.readers.postgres_application_key_issuance_facts_reader import (
    PostgresApplicationKeyIssuanceFactsReader,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_current_issuer_and_empty_application_are_observed_under_coordination(
    database: Database,
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account

    async with database.session() as session, session.begin():
        before = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert before is not None
        facts = await PostgresApplicationKeyIssuanceFactsReader(session).lock_for_issue(
            access=creator.access,
            project_id=project.project_id,
            application_principal_id=account.principal_id,
        )
        assert facts is not None
        assert facts.organization_id == creator.organization_id
        assert facts.actor.principal.id == creator.access.actor_principal_id
        assert facts.application_principal.id == account.principal_id
        assert facts.actor.has_exact_action_grant and facts.actor.is_project_member
        assert facts.is_application_project_member
        assert facts.has_all_action_delegation and facts.manages_all_groups
        assert facts.usable_key_count == 0 and facts.access_revision == account.access_revision
        assert facts.checked_at >= before and facts.checked_at.utcoffset() == timedelta(0)


async def test_count_uses_parent_keys_across_adapters_and_excludes_expired_and_revoked(
    database: Database,
) -> None:
    seed = await seed_application_key(database)
    account = seed.account
    for expired in (True, False):
        credential = await store_application_key(
            database,
            principal_id=account.principal_id,
            organization_id=account.organization_id,
            project_id=account.project_id,
            issued_by=seed.creator_access.actor_principal_id,
        )
        async with database.session() as session, session.begin():
            now = func.clock_timestamp(type_=DateTime(timezone=True))
            statement = update(ApplicationKeyRow).where(
                ApplicationKeyRow.key_id == credential.key_id.value
            )
            await session.execute(
                statement.values(expires_at=now) if expired else statement.values(revoked_at=now)
            )
    await store_application_key(
        database,
        principal_id=account.principal_id,
        organization_id=account.organization_id,
        project_id=account.project_id,
        issued_by=seed.creator_access.actor_principal_id,
        audience="https://another.example.test/resource",
        adapters=(ApplicationKeyAdapter.MCP, ApplicationKeyAdapter.HTTP),
    )

    async with database.session() as session, session.begin():
        facts = await PostgresApplicationKeyIssuanceFactsReader(session).lock_for_issue(
            access=seed.creator_access,
            project_id=account.project_id,
            application_principal_id=account.principal_id,
        )
        assert facts is not None and facts.usable_key_count == 2


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_issuance_refuses_snapshot_isolation_before_observing_authority(
    database: Database, isolation: str
) -> None:
    seed = await seed_application_key(database)
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": isolation})
        with pytest.raises(RuntimeError, match="READ COMMITTED"):
            await PostgresApplicationKeyIssuanceFactsReader(session).lock_for_issue(
                access=seed.creator_access,
                project_id=seed.account.project_id,
                application_principal_id=seed.account.principal_id,
            )


@pytest.mark.parametrize(
    "loss", ["issue", "issuer-membership", "issuer-status", "project", "account", "app-membership"]
)
async def test_current_issuer_and_application_losses_remain_explicit_facts(
    database: Database, loss: str
) -> None:
    seed = await seed_application_key(database)
    account, issuer = seed.account, seed.creator_access.actor_principal_id
    async with database.session() as session, session.begin():
        if loss == "issue":
            await session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.project_id == account.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == account.principal_id.value,
                    ApplicationActionGrantRow.recipient_principal_id == issuer.value,
                    ApplicationActionGrantRow.action == ApplicationAccountAction.ISSUE_KEYS.value,
                )
            )
        elif loss in ("issuer-membership", "app-membership"):
            if loss == "issuer-membership":
                # A real departure removes the membership's grant references first.
                await session.execute(
                    delete(ProjectActionGrantRow).where(
                        ProjectActionGrantRow.project_id == account.project_id.value,
                        ProjectActionGrantRow.recipient_principal_id == issuer.value,
                    )
                )
                await session.execute(
                    delete(ApplicationActionGrantRow).where(
                        ApplicationActionGrantRow.project_id == account.project_id.value,
                        ApplicationActionGrantRow.recipient_principal_id == issuer.value,
                    )
                )
            await session.execute(
                delete(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == account.project_id.value,
                    ProjectMembershipRow.principal_id
                    == (issuer if loss == "issuer-membership" else account.principal_id).value,
                )
            )
        elif loss in ("issuer-status", "account"):
            await session.execute(
                update(PrincipalRow)
                .where(
                    PrincipalRow.id
                    == (issuer if loss == "issuer-status" else account.principal_id).value
                )
                .values(status=PrincipalStatus.SUSPENDED)
            )
        else:
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == account.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )

    async with database.session() as session, session.begin():
        facts = await PostgresApplicationKeyIssuanceFactsReader(session).lock_for_issue(
            access=seed.creator_access,
            project_id=account.project_id,
            application_principal_id=account.principal_id,
        )
    assert facts is not None
    assert facts.actor.has_exact_action_grant is (loss not in ("issue", "issuer-membership"))
    assert facts.actor.is_project_member is (loss != "issuer-membership")
    assert facts.actor.principal.status is (
        PrincipalStatus.SUSPENDED if loss == "issuer-status" else PrincipalStatus.ACTIVE
    )
    assert facts.actor.project_status is (
        ProjectStatus.DELETING if loss == "project" else ProjectStatus.ACTIVE
    )
    assert facts.application_principal.status is (
        PrincipalStatus.SUSPENDED if loss == "account" else PrincipalStatus.ACTIVE
    )
    assert facts.is_application_project_member is (loss != "app-membership")


@pytest.mark.parametrize("can_grant", [None, False, True], ids=["absent", "use-only", "delegate"])
async def test_every_held_project_action_needs_exact_issuer_delegation(
    database: Database, can_grant: bool | None
) -> None:
    seed = await seed_application_key(database)
    account, issuer = seed.account, seed.creator_access.actor_principal_id
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=account.project_id.value,
                recipient_principal_id=account.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ProjectAction.INSPECT_BUDGET.value,
                can_grant=False,
            )
        )
        grant = (
            ProjectActionGrantRow.project_id == account.project_id.value,
            ProjectActionGrantRow.recipient_principal_id == issuer.value,
            ProjectActionGrantRow.action == ProjectAction.INSPECT_BUDGET.value,
        )
        if can_grant is None:
            await session.execute(delete(ProjectActionGrantRow).where(*grant))
        else:
            await session.execute(
                update(ProjectActionGrantRow).where(*grant).values(can_grant=can_grant)
            )

    async with database.session() as session, session.begin():
        facts = await PostgresApplicationKeyIssuanceFactsReader(session).lock_for_issue(
            access=seed.creator_access,
            project_id=account.project_id,
            application_principal_id=account.principal_id,
        )
    assert facts is not None and facts.actor.has_exact_action_grant
    assert facts.has_all_action_delegation is (can_grant is True)


@pytest.mark.parametrize("can_grant", [None, False, True], ids=["absent", "use-only", "delegate"])
async def test_group_action_delegation_does_not_follow_group_management(
    database: Database, can_grant: bool | None
) -> None:
    seed = await seed_application_key(database)
    account, issuer = seed.account, seed.creator_access.actor_principal_id
    group = (
        await create_group(
            database, seed.creator_access, account.project_id, revision=account.access_revision
        )
    ).group
    async with database.session() as session, session.begin():
        session.add(
            GroupActionGrantRow(
                project_id=account.project_id.value,
                group_id=group.group_id.value,
                recipient_principal_id=account.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action="add-documents",
                can_grant=False,
            )
        )
        if can_grant is not None:
            session.add(
                GroupActionGrantRow(
                    project_id=account.project_id.value,
                    group_id=group.group_id.value,
                    recipient_principal_id=issuer.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="add-documents",
                    can_grant=can_grant,
                )
            )

    async with database.session() as session, session.begin():
        facts = await PostgresApplicationKeyIssuanceFactsReader(session).lock_for_issue(
            access=seed.creator_access,
            project_id=account.project_id,
            application_principal_id=account.principal_id,
        )
    assert facts is not None
    assert facts.manages_all_groups
    assert facts.has_all_action_delegation is (can_grant is True)


@pytest.mark.parametrize("managed", [False, True])
async def test_each_application_group_requires_current_issuer_management(
    database: Database, managed: bool
) -> None:
    seed = await seed_application_key(database)
    account = seed.account
    created = await create_group(
        database, seed.creator_access, account.project_id, revision=account.access_revision
    )
    await change_group(
        database,
        seed.creator_access,
        created.group,
        account.principal_id,
        AccessGroupChangeKind.ADD_MEMBER,
        created.group.access_revision,
        "app-group-membership",
    )
    if not managed:
        async with database.session() as session, session.begin():
            await session.execute(
                delete(GroupManagerRow).where(
                    GroupManagerRow.project_id == account.project_id.value,
                    GroupManagerRow.group_id == created.group.group_id.value,
                    GroupManagerRow.principal_id == seed.creator_access.actor_principal_id.value,
                )
            )

    async with database.session() as session, session.begin():
        facts = await PostgresApplicationKeyIssuanceFactsReader(session).lock_for_issue(
            access=seed.creator_access,
            project_id=account.project_id,
            application_principal_id=account.principal_id,
        )
    assert facts is not None and facts.has_all_action_delegation
    assert facts.manages_all_groups is managed


async def test_account_bound_to_another_existing_project_is_hidden(database: Database) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    foreign = (
        await create_project(database, creator, name="other-project", key="other-project")
    ).project
    async with database.session() as session, session.begin():
        assert (
            await PostgresApplicationKeyIssuanceFactsReader(session).lock_for_issue(
                access=creator.access,
                project_id=foreign.project_id,
                application_principal_id=account.principal_id,
            )
            is None
        )


@pytest.mark.parametrize("coordination", ["project", "key"])
async def test_waiting_issuance_observes_current_authority_and_post_wait_expiry(
    database: Database, coordination: str
) -> None:
    seed = await seed_application_key(database)
    account = seed.account
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    task: asyncio.Task[ApplicationKeyIssuanceFactsDTO | None] | None = None
    async with database.session() as caller, caller.begin():
        try:
            async with database.session() as holder, holder.begin():
                holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
                assert holder_pid is not None
                if coordination == "project":
                    await holder.scalar(
                        select(ProjectRow.id)
                        .where(ProjectRow.id == account.project_id.value)
                        .with_for_update()
                    )
                else:
                    await holder.execute(
                        update(ApplicationKeyRow)
                        .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                        .values(http_audience="https://api.test")
                    )
                task = asyncio.create_task(
                    PostgresApplicationKeyIssuanceFactsReader(caller).lock_for_issue(
                        access=seed.creator_access,
                        project_id=account.project_id,
                        application_principal_id=account.principal_id,
                    )
                )
                blocked = None
                async with asyncio.timeout(3):
                    while not task.done():
                        async with database.session() as observer:
                            blocked = await observer.scalar(
                                select(pid)
                                .select_from(activity)
                                .where(
                                    name == func.current_database(type_=String()),
                                    func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                        [holder_pid]
                                    ),
                                )
                            )
                        if blocked is not None:
                            break
                        await asyncio.sleep(0.01)
                if blocked is None:
                    task.result()
                    pytest.fail("Issuance bypassed the required coordination lock.")
                released_at = await holder.scalar(
                    select(func.clock_timestamp(type_=DateTime(timezone=True)))
                )
                assert released_at is not None
                if coordination == "project":
                    await holder.execute(
                        delete(ApplicationActionGrantRow).where(
                            ApplicationActionGrantRow.project_id == account.project_id.value,
                            ApplicationActionGrantRow.application_principal_id
                            == account.principal_id.value,
                            ApplicationActionGrantRow.recipient_principal_id
                            == seed.creator_access.actor_principal_id.value,
                            ApplicationActionGrantRow.action
                            == ApplicationAccountAction.ISSUE_KEYS.value,
                        )
                    )
                else:
                    await holder.execute(
                        update(ApplicationKeyRow)
                        .where(ApplicationKeyRow.key_id == seed.credential.key_id.value)
                        .values(expires_at=released_at)
                    )
            facts = await task
            assert facts is not None and facts.checked_at >= released_at
            assert facts.actor.has_exact_action_grant is (coordination != "project")
            assert facts.usable_key_count == (0 if coordination == "key" else 1)
        finally:
            if task is not None:
                async with asyncio.timeout(3):
                    if not task.done():
                        task.cancel()
                    outcome = (await asyncio.shield(asyncio.gather(task, return_exceptions=True)))[
                        0
                    ]
                if isinstance(outcome, BaseException) and not isinstance(
                    outcome, asyncio.CancelledError
                ):
                    raise outcome


async def test_absent_original_returns_no_plaintext_or_replacement(database: Database) -> None:
    seed = await seed_application_key(database)
    async with database.session() as session, session.begin():
        assert (
            await PostgresApplicationKeyIssuanceFactsReader(session).read_original(
                organization_id=seed.account.organization_id,
                project_id=seed.account.project_id,
                application_principal_id=seed.account.principal_id,
                issuer_principal_id=seed.creator_access.actor_principal_id,
                operation_id=OperationId(str(uuid4())),
            )
            is None
        )
