"""Qualify local effects only, without claiming authentic Project-deletion admission."""

import asyncio
import os
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, Integer, String, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from tests.support.application_account_scenarios import create_account
from tests.support.application_key_scenarios import store_application_key
from tests.support.project_creation_scenarios import (
    ProjectCreationSeedDTO,
    create_project,
    seed_project_creator,
)

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.application_key_creation_dto import (
    ApplicationKeyCreationDTO,
)
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.application_key_issuance_settings import (
    ApplicationKeyIssuanceSettings,
)
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_key_issuance_writer import (
    PostgresApplicationKeyIssuanceWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_application_shutdown_effects_writer import (
    PostgresProjectApplicationShutdownEffectsWriter,
)
from inframeld_backend.bootstrap.application_key_composition import open_application_key_issuance
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]
HTTP = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)
MCP = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://mcp.test/mcp"), ApplicationKeyAdapter.MCP
)


@dataclass(frozen=True, slots=True)
class ShutdownScopeDTO:
    creator: ProjectCreationSeedDTO
    installation_id: InstallationId
    accounts: tuple[CreatedApplicationAccountDTO, CreatedApplicationAccountDTO]
    outside: CreatedApplicationAccountDTO
    credentials: tuple[ApplicationKeyCredential, ...]
    outside_credential: ApplicationKeyCredential
    group_id: UUID
    old_revocation: datetime
    expired_at: datetime
    access_revision: int
    audit_ids: frozenset[UUID]


@pytest_asyncio.fixture
async def shutdown_scope(database: Database) -> ShutdownScopeDTO:
    """Build real accounts and keys, with controlled lifecycle/history observations."""
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    async with database.session() as session:
        organization_revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == creator.organization_id.value
            )
        )
    assert organization_revision is not None
    other = (
        await create_project(
            database,
            replace(creator, access_revision=organization_revision),
            name="unrelated",
            key="create-unrelated",
        )
    ).project
    first = (await create_account(database, creator.access, project.project_id)).account
    second = (
        await create_account(
            database,
            creator.access,
            project.project_id,
            revision=first.access_revision,
            name="second-bot",
            key="create-second-bot",
        )
    ).account
    outside = (
        await create_account(database, creator.access, other.project_id, key="outside-bot")
    ).account
    credentials = tuple(
        [
            await store_application_key(
                database,
                principal_id=account.principal_id,
                organization_id=account.organization_id,
                project_id=account.project_id,
                audience=MCP.audience.value
                if adapters == (ApplicationKeyAdapter.MCP,)
                else HTTP.audience.value,
                adapters=adapters,
            )
            for account, adapters in (
                (first, (ApplicationKeyAdapter.HTTP,)),
                (first, (ApplicationKeyAdapter.HTTP,)),
                (first, (ApplicationKeyAdapter.HTTP,)),
                (second, (ApplicationKeyAdapter.MCP,)),
                (second, (ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP)),
            )
        ]
    )
    outside_credential = await store_application_key(
        database,
        principal_id=outside.principal_id,
        organization_id=outside.organization_id,
        project_id=outside.project_id,
    )
    group_id = uuid4()
    async with database.session() as session, session.begin():
        now = await session.scalar(select(func.clock_timestamp(type_=DateTime(timezone=True))))
        assert now is not None
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == credentials[1].key_id.value)
            .values(created_at=now - timedelta(days=2), expires_at=now - timedelta(days=1))
        )
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == credentials[2].key_id.value)
            .values(revoked_at=now)
        )
        await session.execute(
            update(ApplicationKeyRow)
            .where(ApplicationKeyRow.key_id == credentials[4].key_id.value)
            .values(mcp_audience=MCP.audience.value)
        )
        session.add(
            AccessGroupRow(id=group_id, project_id=project.project_id.value, name="Private")
        )
        await session.flush()
        for principal_id in (creator.access.actor_principal_id.value, first.principal_id.value):
            session.add(
                GroupMembershipRow(
                    project_id=project.project_id.value,
                    group_id=group_id,
                    principal_id=principal_id,
                )
            )
        await session.flush()
        session.add(
            GroupManagerRow(
                project_id=project.project_id.value,
                group_id=group_id,
                principal_id=creator.access.actor_principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        session.add(
            GroupActionGrantRow(
                project_id=project.project_id.value,
                group_id=group_id,
                recipient_principal_id=creator.access.actor_principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action="read-documents",
                can_grant=True,
            )
        )
        session.add(
            GroupActionGrantRow(
                project_id=project.project_id.value,
                group_id=group_id,
                recipient_principal_id=first.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action="read-documents",
                can_grant=False,
            )
        )
        session.add(
            ProjectActionGrantRow(
                project_id=project.project_id.value,
                recipient_principal_id=first.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ProjectAction.INSPECT_BUDGET.value,
                can_grant=False,
            )
        )
    async with database.session() as session:
        audit_ids = frozenset(await session.scalars(select(AccessAuditEventRow.id)))
    verifier = PostgresApplicationKeyVerifier(database)
    assert await verifier.verify(credentials[0], profile=HTTP) is not None
    assert await verifier.verify(credentials[3], profile=MCP) is not None
    assert await verifier.verify(credentials[4], profile=HTTP) is not None
    assert await verifier.verify(credentials[4], profile=MCP) is not None
    assert await verifier.verify(outside_credential, profile=HTTP) is not None
    return ShutdownScopeDTO(
        creator,
        await PostgresInstallationIdentityReader(database).read(),
        (first, second),
        outside,
        credentials,
        outside_credential,
        group_id,
        now,
        now - timedelta(days=1),
        second.access_revision,
        audit_ids,
    )


async def apply_in_controlled_transaction(database: Database, scope: ShutdownScopeDTO) -> bool:
    """Set only an effects-layer precondition, never a genuine deletion admission."""
    account = scope.accounts[0]
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == account.project_id.value)
            .values(status=ProjectStatus.DELETING)
        )
        return await PostgresProjectApplicationShutdownEffectsWriter(session).shutdown(
            installation_id=scope.installation_id,
            organization_id=account.organization_id,
            project_id=account.project_id,
        )


async def assert_exact_effects(database: Database, scope: ShutdownScopeDTO) -> None:
    project_id = scope.accounts[0].project_id.value
    application_ids = tuple(account.principal_id.value for account in scope.accounts)
    async with database.session() as session:
        retained_keys = (
            await session.scalars(
                select(ApplicationKeyRow).where(
                    ApplicationKeyRow.application_principal_id.in_(application_ids)
                )
            )
        ).all()
        assert {key.key_id for key in retained_keys} == {
            credential.key_id.value for credential in scope.credentials
        }
        assert {
            key.key_id: (tuple(key.allowed_adapters), key.http_audience, key.mcp_audience)
            for key in retained_keys
        } == {
            scope.credentials[0].key_id.value: (("http",), HTTP.audience.value, None),
            scope.credentials[1].key_id.value: (("http",), HTTP.audience.value, None),
            scope.credentials[2].key_id.value: (("http",), HTTP.audience.value, None),
            scope.credentials[3].key_id.value: (("mcp",), None, MCP.audience.value),
            scope.credentials[4].key_id.value: (
                ("http", "mcp"),
                HTTP.audience.value,
                MCP.audience.value,
            ),
        }
        for credential in scope.credentials:
            key = next(key for key in retained_keys if key.key_id == credential.key_id.value)
            if key.verifier != sha256(credential.value.encode("ascii")).digest():
                raise AssertionError("Shutdown changed a retained credential verifier.")
        assert (
            next(
                key for key in retained_keys if key.key_id == scope.credentials[1].key_id.value
            ).expires_at
            == scope.expired_at
        )
        assert set(
            (
                await session.execute(
                    select(PrincipalRow.id, PrincipalRow.status).where(
                        PrincipalRow.id.in_(application_ids)
                    )
                )
            ).tuples()
        ) == {(identity, PrincipalStatus.RETIRED) for identity in application_ids}
        assert len(
            (
                await session.scalars(
                    select(ApplicationAccountRow).where(
                        ApplicationAccountRow.principal_id.in_(application_ids)
                    )
                )
            ).all()
        ) == len(application_ids)
        assert set(
            (
                await session.execute(
                    select(
                        ApplicationAccountRow.principal_id, ApplicationAccountRow.resource_name
                    ).where(ApplicationAccountRow.principal_id.in_(application_ids))
                )
            ).tuples()
        ) == {(account.principal_id.value, account.name.value) for account in scope.accounts}
        assert not (
            await session.scalars(
                select(ApplicationKeyRow.key_id).where(
                    ApplicationKeyRow.application_principal_id.in_(application_ids),
                    ApplicationKeyRow.revoked_at.is_(None),
                )
            )
        ).all()
        assert (
            await session.scalar(
                select(ApplicationKeyRow.revoked_at).where(
                    ApplicationKeyRow.key_id == scope.credentials[2].key_id.value
                )
            )
            == scope.old_revocation
        )
        assert not (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == project_id,
                    ProjectActionGrantRow.recipient_principal_id.in_(application_ids),
                )
            )
        ).all()
        assert not (
            await session.scalars(
                select(GroupActionGrantRow).where(
                    GroupActionGrantRow.project_id == project_id,
                    GroupActionGrantRow.recipient_principal_id.in_(application_ids),
                )
            )
        ).all()
        assert not (
            await session.scalars(
                select(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.project_id == project_id,
                    ApplicationActionGrantRow.application_principal_id.in_(application_ids),
                )
            )
        ).all()
        assert not (
            await session.scalars(
                select(GroupMembershipRow).where(
                    GroupMembershipRow.project_id == project_id,
                    GroupMembershipRow.principal_id.in_(application_ids),
                )
            )
        ).all()
        assert not (
            await session.scalars(
                select(ProjectMembershipRow).where(
                    ProjectMembershipRow.project_id == project_id,
                    ProjectMembershipRow.principal_id.in_(application_ids),
                )
            )
        ).all()
        human = scope.creator.access.actor_principal_id.value
        assert (
            await session.scalar(select(PrincipalRow.status).where(PrincipalRow.id == human))
            is PrincipalStatus.ACTIVE
        )
        assert (
            await session.get(GroupMembershipRow, (project_id, scope.group_id, human)) is not None
        )
        assert await session.get(GroupManagerRow, (project_id, scope.group_id, human)) is not None
        assert await session.get(AccessGroupRow, scope.group_id) is not None
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project_id)
            )
            == scope.access_revision
        )
        assert frozenset(await session.scalars(select(AccessAuditEventRow.id))) == scope.audit_ids
        assert (
            await session.scalar(
                select(PrincipalRow.status).where(
                    PrincipalRow.id == scope.outside.principal_id.value
                )
            )
            is PrincipalStatus.ACTIVE
        )
        assert (
            await session.get(
                ProjectMembershipRow,
                (scope.outside.project_id.value, scope.outside.principal_id.value),
            )
            is not None
        )
    verifier = PostgresApplicationKeyVerifier(database)
    for credential, profile in (
        (scope.credentials[0], HTTP),
        (scope.credentials[1], HTTP),
        (scope.credentials[2], HTTP),
        (scope.credentials[3], MCP),
        (scope.credentials[4], HTTP),
        (scope.credentials[4], MCP),
    ):
        assert await verifier.verify(credential, profile=profile) is None
    assert await verifier.verify(scope.outside_credential, profile=HTTP) is not None


async def test_exact_project_effects_revoke_every_key_and_preserve_other_owners(
    database: Database, shutdown_scope: ShutdownScopeDTO
) -> None:
    assert await apply_in_controlled_transaction(database, shutdown_scope) is True
    await assert_exact_effects(database, shutdown_scope)


async def test_accounts_without_project_membership_are_still_shutdown(
    database: Database, shutdown_scope: ShutdownScopeDTO
) -> None:
    account = shutdown_scope.accounts[1]
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.project_id == account.project_id.value,
                ProjectMembershipRow.principal_id == account.principal_id.value,
            )
        )
    assert await apply_in_controlled_transaction(database, shutdown_scope) is True
    await assert_exact_effects(database, shutdown_scope)


async def test_repeat_checks_local_noop_without_revision_audit_or_checkpoint_completion(
    database: Database, shutdown_scope: ShutdownScopeDTO
) -> None:
    assert await apply_in_controlled_transaction(database, shutdown_scope) is True
    assert await apply_in_controlled_transaction(database, shutdown_scope) is False
    await assert_exact_effects(database, shutdown_scope)


async def test_caller_rollback_restores_all_uncommitted_shutdown_effects(
    database: Database, shutdown_scope: ShutdownScopeDTO
) -> None:
    account = shutdown_scope.accounts[0]
    async with database.session() as session:
        transaction = await session.begin()
        try:
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == account.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )
            assert (
                await PostgresProjectApplicationShutdownEffectsWriter(session).shutdown(
                    installation_id=shutdown_scope.installation_id,
                    organization_id=account.organization_id,
                    project_id=account.project_id,
                )
                is True
            )
        finally:
            await transaction.rollback()
    async with database.session() as session:
        assert (
            await session.scalar(
                select(PrincipalRow.status).where(PrincipalRow.id == account.principal_id.value)
            )
            is PrincipalStatus.ACTIVE
        )
        assert (
            await session.scalar(
                select(ProjectRow.status).where(ProjectRow.id == account.project_id.value)
            )
            is ProjectStatus.ACTIVE
        )
        assert (
            await session.scalar(
                select(ApplicationKeyRow.revoked_at).where(
                    ApplicationKeyRow.key_id == shutdown_scope.credentials[0].key_id.value
                )
            )
            is None
        )
        assert (
            await session.scalars(
                select(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.application_principal_id == account.principal_id.value
                )
            )
        ).all()
        assert (
            frozenset(await session.scalars(select(AccessAuditEventRow.id)))
            == shutdown_scope.audit_ids
        )


@pytest.mark.parametrize("invalid", ["installation", "organization", "project", "active"])
async def test_wrong_scope_or_lifecycle_is_not_an_admission_certificate(
    database: Database, shutdown_scope: ShutdownScopeDTO, invalid: str
) -> None:
    account = shutdown_scope.accounts[0]
    async with database.session() as session, session.begin():
        if invalid != "active":
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == account.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )
        with pytest.raises(RuntimeError) as raised:
            await PostgresProjectApplicationShutdownEffectsWriter(session).shutdown(
                installation_id=InstallationId(uuid4())
                if invalid == "installation"
                else shutdown_scope.installation_id,
                organization_id=OrganizationId(uuid4())
                if invalid == "organization"
                else account.organization_id,
                project_id=ProjectId(uuid4()) if invalid == "project" else account.project_id,
            )
        assert type(raised.value) is RuntimeError
        assert (
            await session.scalar(
                select(PrincipalRow.status).where(PrincipalRow.id == account.principal_id.value)
            )
            is PrincipalStatus.ACTIVE
        )
        assert (
            await session.scalar(
                select(ApplicationKeyRow.revoked_at).where(
                    ApplicationKeyRow.key_id == shutdown_scope.credentials[0].key_id.value
                )
            )
            is None
        )


@pytest.mark.parametrize("state", ["absent", "repeatable-read"])
async def test_writer_requires_the_callers_active_read_committed_transaction(
    database: Database, shutdown_scope: ShutdownScopeDTO, state: str
) -> None:
    account = shutdown_scope.accounts[0]
    async with database.session() as setup, setup.begin():
        await setup.execute(
            update(ProjectRow)
            .where(ProjectRow.id == account.project_id.value)
            .values(status=ProjectStatus.DELETING)
        )
    async with database.session() as session:
        if state == "repeatable-read":
            await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        with pytest.raises(RuntimeError) as raised:
            await PostgresProjectApplicationShutdownEffectsWriter(session).shutdown(
                installation_id=shutdown_scope.installation_id,
                organization_id=account.organization_id,
                project_id=account.project_id,
            )
        assert type(raised.value) is RuntimeError


async def issue_one(database: Database, scope: ShutdownScopeDTO) -> ApplicationKeyIssueResultDTO:
    account = scope.accounts[0]
    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == account.project_id.value)
        )
    assert revision is not None
    fingerprints = ApplicationKeyIssuanceFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"s" * 32))
    )
    async with open_application_key_issuance(
        database,
        fingerprints,
        http_profile=HTTP,
        mcp_profile=None,
        settings=ApplicationKeyIssuanceSettings(),
    ) as issuer:
        return await issuer.issue(
            access=scope.creator.access,
            command=IssueApplicationKeyCommand(
                account.project_id, account.principal_id, (ApplicationKeyAdapter.HTTP,), revision
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}/keys",
                IdempotencyKey("racing-issue"),
            ),
        )


async def wait_for_blocker(database: Database, holder_pid: int | None = None) -> None:
    """Use the existing typed PostgreSQL lock observation, not a guessed delay."""
    pid = column("pid", Integer)
    name = column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(3):
        while True:
            async with database.session() as observer:
                blockers = func.pg_blocking_pids(pid, type_=ARRAY(Integer))
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        blockers.contains([holder_pid])
                        if holder_pid is not None
                        else func.cardinality(blockers) > 0,
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)


async def test_issuance_wins_then_shutdown_revokes_its_new_real_credential(
    database: Database, shutdown_scope: ShutdownScopeDTO, monkeypatch: pytest.MonkeyPatch
) -> None:
    saved, release = asyncio.Event(), asyncio.Event()
    original = PostgresApplicationKeyIssuanceWriter.create

    async def hold_after_create(
        writer: PostgresApplicationKeyIssuanceWriter,
        *,
        key: ApplicationKeyCreationDTO,
        expected_project_revision: int,
    ) -> None:
        await original(writer, key=key, expected_project_revision=expected_project_revision)
        saved.set()
        await release.wait()

    monkeypatch.setattr(PostgresApplicationKeyIssuanceWriter, "create", hold_after_create)
    issuance: asyncio.Task[ApplicationKeyIssueResultDTO] | None = None
    shutdown: asyncio.Task[bool] | None = None
    work_error: BaseException | None = None
    try:
        issuance = asyncio.create_task(issue_one(database, shutdown_scope))
        async with asyncio.timeout(3):
            await saved.wait()
        shutdown = asyncio.create_task(apply_in_controlled_transaction(database, shutdown_scope))
        await wait_for_blocker(database)
        release.set()
        async with asyncio.timeout(3):
            await asyncio.shield(issuance)
            await asyncio.shield(shutdown)
    except BaseException as error:
        work_error = error
        raise
    finally:
        release.set()
        active = [task for task in (issuance, shutdown) if task is not None]
        cleanup_errors: list[BaseException] = []
        try:
            async with asyncio.timeout(3):
                for task in active:
                    if not task.done():
                        task.cancel()
                if issuance is not None and shutdown is not None:
                    outcomes = await asyncio.shield(
                        asyncio.gather(issuance, shutdown, return_exceptions=True)
                    )
                elif issuance is not None:
                    outcomes = await asyncio.shield(
                        asyncio.gather(issuance, return_exceptions=True)
                    )
                elif shutdown is not None:
                    outcomes = await asyncio.shield(
                        asyncio.gather(shutdown, return_exceptions=True)
                    )
                else:
                    outcomes = ()
            for outcome in outcomes:
                if (
                    isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not work_error
                    and all(outcome is not previous for previous in cleanup_errors)
                ):
                    cleanup_errors.append(outcome)
        except BaseException as error:
            if error is not work_error:
                cleanup_errors.append(error)
        if cleanup_errors:
            raise BaseExceptionGroup(
                "Issuance/shutdown work and task settlement failed",
                ([work_error] if work_error is not None else []) + cleanup_errors,
            ) from None
    assert issuance is not None and shutdown is not None
    issued = issuance.result()
    assert shutdown.result() is True and issued.credential is not None
    assert (
        await PostgresApplicationKeyVerifier(database).verify(issued.credential, profile=HTTP)
        is None
    )


async def test_shutdown_wins_and_real_issuance_rechecks_the_project_block(
    database: Database, shutdown_scope: ShutdownScopeDTO
) -> None:
    account = shutdown_scope.accounts[0]

    async def denied_issuance() -> None:
        with pytest.raises(ResourceNotFoundError):
            await issue_one(database, shutdown_scope)

    async with database.session() as caller:
        transaction = await caller.begin()
        issuance: asyncio.Task[None] | None = None
        work_error: BaseException | None = None
        try:
            await caller.execute(
                update(ProjectRow)
                .where(ProjectRow.id == account.project_id.value)
                .values(status=ProjectStatus.DELETING)
            )
            assert (
                await PostgresProjectApplicationShutdownEffectsWriter(caller).shutdown(
                    installation_id=shutdown_scope.installation_id,
                    organization_id=account.organization_id,
                    project_id=account.project_id,
                )
                is True
            )
            holder_pid = await caller.scalar(select(func.pg_backend_pid(type_=Integer())))
            assert holder_pid is not None
            issuance = asyncio.create_task(denied_issuance())
            await wait_for_blocker(database, holder_pid)
            async with asyncio.timeout(3):
                await transaction.commit()
                await asyncio.shield(issuance)
        except BaseException as error:
            work_error = error
            raise
        finally:
            cleanup_errors: list[BaseException] = []
            if issuance is not None and not issuance.done():
                issuance.cancel()
            try:
                async with asyncio.timeout(3):
                    if transaction.is_active:
                        await transaction.rollback()
            except BaseException as error:
                if error is not work_error:
                    cleanup_errors.append(error)
            if issuance is not None:
                try:
                    async with asyncio.timeout(3):
                        outcome = (
                            await asyncio.shield(asyncio.gather(issuance, return_exceptions=True))
                        )[0]
                    if (
                        isinstance(outcome, BaseException)
                        and not isinstance(outcome, asyncio.CancelledError)
                        and outcome is not work_error
                        and all(outcome is not previous for previous in cleanup_errors)
                    ):
                        cleanup_errors.append(outcome)
                except BaseException as error:
                    if error is not work_error:
                        cleanup_errors.append(error)
            if cleanup_errors:
                raise BaseExceptionGroup(
                    "Shutdown/issuance work, rollback and task settlement failed",
                    ([work_error] if work_error is not None else []) + cleanup_errors,
                ) from None
    await assert_exact_effects(database, shutdown_scope)
