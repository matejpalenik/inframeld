"""Qualify issuance effects and safe replay through the actual transaction boundary."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from hmac import compare_digest
from json import dumps

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import DateTime, event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.access_group_scenarios import change_group, create_group
from tests.support.application_account_scenarios import create_account
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
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
from inframeld_backend.access.application.dtos.current_application_session_dto import (
    CurrentApplicationSessionDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.services.application_key_issuance_service import (
    ApplicationKeyIssuanceService,
)
from inframeld_backend.access.application.services.application_session_service import (
    ApplicationSessionService,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_key_issuance_facts_reader import (
    PostgresApplicationKeyIssuanceFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_key_issuance_result_row import (
    ApplicationKeyIssuanceResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.verifiers.postgres_application_key_verifier import (
    PostgresApplicationKeyVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_key_issuance_writer import (
    PostgresApplicationKeyIssuanceWriter,
)
from inframeld_backend.bootstrap.access_group_composition import open_access_group_read
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import StaleRevisionError
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

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


def _service(
    session: AsyncSession,
    *,
    http_profile: ApplicationKeyVerificationProfileDTO | None = HTTP,
    mcp_profile: ApplicationKeyVerificationProfileDTO | None = MCP,
    default_lifetime_seconds: int = 90 * 86400,
    maximum_lifetime_seconds: int = 365 * 86400,
) -> ApplicationKeyIssuanceService:
    return ApplicationKeyIssuanceService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        issuance_facts_reader=PostgresApplicationKeyIssuanceFactsReader(session),
        issuance_writer=PostgresApplicationKeyIssuanceWriter(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        issuance_fingerprint_service=ApplicationKeyIssuanceFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ),
        http_profile=http_profile,
        mcp_profile=mcp_profile,
        default_lifetime_seconds=default_lifetime_seconds,
        maximum_lifetime_seconds=maximum_lifetime_seconds,
    )


def _request(
    account: CreatedApplicationAccountDTO,
) -> tuple[IssueApplicationKeyCommand, IdempotencyContextDTO]:
    command = IssueApplicationKeyCommand(
        project_id=account.project_id,
        application_principal_id=account.principal_id,
        allowed_adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP),
        expected_access_revision=account.access_revision,
    )
    context = IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}/keys",
        IdempotencyKey("issue-original"),
    )
    return command, context


@pytest.mark.parametrize(
    "adapters",
    [
        (ApplicationKeyAdapter.HTTP,),
        (ApplicationKeyAdapter.MCP,),
        (ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP),
        (ApplicationKeyAdapter.MCP, ApplicationKeyAdapter.HTTP),
    ],
)
async def test_issue_commits_one_key_revision_audit_and_safe_original(
    database: Database, adapters: tuple[ApplicationKeyAdapter, ...]
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    command, context = _request(account)
    command = replace(command, allowed_adapters=adapters)
    async with database.session() as session:
        first = await _service(session).issue(
            access=creator.access, command=command, context=context
        )
    assert first.credential is not None and first.operation.created
    assert first.original.metadata.key_id == first.credential.key_id
    assert first.original.metadata.allowed_adapters == command.allowed_adapters
    assert first.original.metadata.expires_at - first.original.metadata.created_at == timedelta(
        days=90
    )
    assert first.original.access_revision == account.access_revision + 1

    async with database.session() as session:
        key = await session.get(ApplicationKeyRow, first.credential.key_id.value)
        original = await session.get(
            ApplicationKeyIssuanceResultRow, first.operation.operation_id.value
        )
        reservation = await session.get(
            IdempotencyReservationRow, first.operation.operation_id.value
        )
        audit = await session.scalar(
            select(AccessAuditEventRow).where(
                AccessAuditEventRow.correlation_id == first.operation.operation_id.value,
                AccessAuditEventRow.event_type == "application_key_issued",
            )
        )
        assert key is not None and compare_digest(key.verifier, first.credential.digest())
        assert original is not None and original.key_id == key.key_id
        assert (
            original.allowed_adapters == [adapter.value for adapter in adapters]
            and original.revoked_at is None
        )
        assert key.http_audience == (
            HTTP.audience.value if ApplicationKeyAdapter.HTTP in adapters else None
        )
        assert key.mcp_audience == (
            MCP.audience.value if ApplicationKeyAdapter.MCP in adapters else None
        )
        assert reservation is not None and reservation.state is OperationReservationState.REPLAYABLE
        assert reservation.replay_kind is OperationReplayKind.ISSUED_SECRET
        assert audit is not None and audit.affected_principal_id == account.principal_id.value
        assert first.credential.value not in dumps(audit.after_values)
        assert "verifier" not in dumps(audit.after_values)
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == first.original.access_revision
        )
    async with database.session() as session:
        replay = await _service(session).issue(
            access=creator.access, command=command, context=context
        )
    assert replay.credential is None and not replay.operation.created
    assert (
        replay.original == first.original
        and replay.operation.operation_id == first.operation.operation_id
    )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ApplicationKeyRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationKeyIssuanceResultRow))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "application_key_issued")
            )
            == 1
        )

    for profile in (HTTP, MCP):
        verifier = PostgresApplicationKeyVerifier(database)
        verified = await verifier.verify(first.credential, profile=profile)
        if profile.adapter not in adapters:
            assert verified is None
            continue
        assert verified is not None and verified.principal_id == account.principal_id
        facts = PostgresApplicationAuthenticationFactsReader(database)
        access = await ApplicationAuthenticationService(
            key_verifier=verifier, authentication_facts_reader=facts, verification_profile=profile
        ).authenticate(first.credential)
        assert await ApplicationSessionService(
            authentication_facts_reader=facts, verification_profile=profile
        ).read(access=access) == CurrentApplicationSessionDTO(
            account.principal_id, account.project_id
        )


@pytest.mark.parametrize("profile", [HTTP, MCP], ids=["http", "mcp"])
@pytest.mark.parametrize("selected", [False, True], ids=["other-slot", "own-slot"])
async def test_issued_dual_key_uses_trusted_adapter_in_every_current_fact_reader(
    database: Database, profile: ApplicationKeyVerificationProfileDTO, selected: bool
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    group = await create_group(
        database, creator.access, project.project_id, revision=account.access_revision
    )
    member = await change_group(
        database,
        creator.access,
        group.group,
        account.principal_id,
        AccessGroupChangeKind.ADD_MEMBER,
        group.group.access_revision,
        "app-member",
    )
    async with database.session() as session, session.begin():
        session.add(
            ProjectActionGrantRow(
                project_id=project.project_id.value,
                recipient_principal_id=account.principal_id.value,
                recipient_kind=PrincipalKind.APPLICATION,
                action=ProjectAction.INSPECT_BUDGET.value,
                can_grant=False,
            )
        )
    command, context = _request(account)
    command = replace(command, expected_access_revision=member.access_revision)
    async with database.session() as session:
        first = await _service(session).issue(
            access=creator.access, command=command, context=context
        )
    assert first.credential is not None
    facts = PostgresApplicationAuthenticationFactsReader(database)
    verifier = PostgresApplicationKeyVerifier(database)
    access = await ApplicationAuthenticationService(
        key_verifier=verifier, authentication_facts_reader=facts, verification_profile=profile
    ).authenticate(first.credential)
    request = ProjectActionAuthorizationRequestDTO(
        project.project_id, ActionId(ProjectAction.INSPECT_BUDGET.value)
    )

    async def disclose() -> None:
        assert await ApplicationSessionService(
            authentication_facts_reader=facts, verification_profile=profile
        ).read(access=access) == CurrentApplicationSessionDTO(
            account.principal_id, account.project_id
        )
        async with database.session() as session, session.begin():
            scope = await ActionAuthorizationService(
                PostgresProjectActionFactsReader(session, application_key_profile=profile)
            ).require_authorization(access=access, request=request)
            assert scope.project_id == project.project_id
        async with open_access_group_read(database, application_key_profile=profile) as reader:
            observed = await reader.inspect(
                access=access, project_id=project.project_id, selector=group.group.group_id
            )
            assert observed.group_id == group.group.group_id

    await disclose()
    async with database.session() as session, session.begin():
        key = await session.get(ApplicationKeyRow, first.original.metadata.key_id.value)
        assert key is not None
        if (profile.adapter is ApplicationKeyAdapter.HTTP) == selected:
            key.http_audience = "https://changed.test/resource"
        else:
            key.mcp_audience = "https://changed.test/resource"
    if not selected:
        assert await verifier.verify(first.credential, profile=profile) is not None
        await disclose()
        return
    assert await verifier.verify(first.credential, profile=profile) is None
    with pytest.raises(ApplicationKeyCredentialRejectedError):
        await ApplicationSessionService(
            authentication_facts_reader=facts, verification_profile=profile
        ).read(access=access)
    async with database.session() as session, session.begin():
        with pytest.raises(ApplicationKeyCredentialRejectedError):
            await ActionAuthorizationService(
                PostgresProjectActionFactsReader(session, application_key_profile=profile)
            ).require_authorization(access=access, request=request)
    async with open_access_group_read(database, application_key_profile=profile) as reader:
        with pytest.raises(ApplicationKeyCredentialRejectedError):
            await reader.inspect(
                access=access, project_id=project.project_id, selector=group.group.group_id
            )


@pytest.mark.parametrize("failure", ["audit", "before-commit"])
async def test_known_failure_rolls_back_key_revision_audit_original_and_reservation(
    database: Database, failure: str
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    command, context = _request(account)
    async with database.session() as session:

        def reject_audit(current: Session, _context: object, _instances: object) -> None:
            if any(
                isinstance(row, AccessAuditEventRow) and row.event_type == "application_key_issued"
                for row in current.new
            ):
                raise RuntimeError("Controlled required audit failure")

        def reject_commit(_current: Session) -> None:
            raise RuntimeError("Controlled failure before COMMIT")

        hook = "before_flush" if failure == "audit" else "before_commit"
        callback = reject_audit if failure == "audit" else reject_commit
        event.listen(session.sync_session, hook, callback)
        try:
            with pytest.raises(RuntimeError, match="Controlled"):
                await _service(session).issue(
                    access=creator.access, command=command, context=context
                )
        finally:
            event.remove(session.sync_session, hook, callback)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ApplicationKeyRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationKeyIssuanceResultRow))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.requested_route == context.requested_route)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "application_key_issued")
            )
            == 0
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == account.access_revision
        )


async def test_uncertain_commit_acknowledgment_recovers_original_without_replacement(
    database: Database,
) -> None:
    """Lose the application acknowledgment after COMMIT, not a wire-level DB fault."""
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    command, context = _request(account)
    async with database.session() as session:

        def lose_acknowledgment(_current: Session) -> None:
            raise RuntimeError("Controlled lost COMMIT acknowledgment")

        event.listen(session.sync_session, "after_commit", lose_acknowledgment)
        try:
            with pytest.raises(RuntimeError, match="lost COMMIT acknowledgment"):
                await _service(session).issue(
                    access=creator.access, command=command, context=context
                )
        finally:
            event.remove(session.sync_session, "after_commit", lose_acknowledgment)
    async with database.session() as session:
        stored = (await session.scalars(select(ApplicationKeyRow.key_id))).one()
    async with database.session() as session:
        recovered = await _service(session).issue(
            access=creator.access, command=command, context=context
        )
    assert recovered.credential is None and not recovered.operation.created
    assert recovered.original.metadata.key_id.value == stored
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ApplicationKeyRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationKeyIssuanceResultRow))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "application_key_issued")
            )
            == 1
        )


@pytest.mark.parametrize("change", ["revoked", "expired", "configuration", "slot-full"])
async def test_safe_original_precedes_fresh_profiles_lifetimes_and_key_lifecycle(
    database: Database, change: str
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    command, context = _request(account)
    async with database.session() as session:
        first = await _service(session).issue(
            access=creator.access, command=command, context=context
        )
    if change == "slot-full":
        async with database.session() as session:
            await _service(session).issue(
                access=creator.access,
                command=replace(command, expected_access_revision=first.original.access_revision),
                context=replace(context, key=IdempotencyKey("second-key")),
            )
    async with database.session() as session, session.begin():
        now = func.clock_timestamp(type_=DateTime(timezone=True))
        if change == "revoked":
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == first.original.metadata.key_id.value)
                .values(revoked_at=now)
            )
        if change == "expired":
            await session.execute(
                update(ApplicationKeyRow)
                .where(ApplicationKeyRow.key_id == first.original.metadata.key_id.value)
                .values(expires_at=now)
            )
    async with database.session() as session:
        recovered = await _service(
            session,
            http_profile=None,
            mcp_profile=None,
            default_lifetime_seconds=1,
            maximum_lifetime_seconds=1,
        ).issue(access=creator.access, command=command, context=context)
    assert recovered.credential is None and recovered.original == first.original
    assert command.expires_in_seconds is None


async def test_retained_original_prevents_destructive_downgrade(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    command, context = _request(account)
    async with database.session() as session:
        first = await _service(session).issue(
            access=creator.access,
            command=replace(command, allowed_adapters=(ApplicationKeyAdapter.HTTP,)),
            context=context,
        )
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings
    with pytest.raises(RuntimeError, match="Retained application-key issuance originals"):
        alembic_command.downgrade(config, "0027_invitations")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == "0031_project_deletion"
        )
        assert (
            await session.get(ApplicationKeyIssuanceResultRow, first.operation.operation_id.value)
            is not None
        )


@pytest.mark.parametrize("same_request", [False, True], ids=["last-slot", "same-original"])
async def test_competing_issuance_turns_keep_one_parent_limit_and_one_original(
    database: Database, same_request: bool
) -> None:
    creator = await seed_project_creator(database)
    project = (await create_project(database, creator)).project
    account = (await create_account(database, creator.access, project.project_id)).account
    command, context = _request(account)
    if not same_request:
        async with database.session() as session:
            initial = await _service(session).issue(
                access=creator.access, command=command, context=context
            )
        command = replace(command, expected_access_revision=initial.original.access_revision)

    async def issue(index: int) -> ApplicationKeyIssueResultDTO | None:
        request = context if same_request else replace(context, key=IdempotencyKey(f"race-{index}"))
        async with database.session() as session:
            try:
                return await _service(session).issue(
                    access=creator.access, command=command, context=request
                )
            except StaleRevisionError:
                if same_request:
                    raise
                return None

    async with asyncio.TaskGroup() as tasks:
        one, two = tasks.create_task(issue(1)), tasks.create_task(issue(2))
    results = (one.result(), two.result())
    assert sum(result is not None and result.credential is not None for result in results) == 1
    if same_request:
        first, replay = results
        assert first is not None and replay is not None
        assert first.original == replay.original
    else:
        assert sum(result is None for result in results) == 1
    expected = 1 if same_request else 2
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ApplicationKeyRow)) == expected
        assert (
            await session.scalar(select(func.count()).select_from(ApplicationKeyIssuanceResultRow))
            == expected
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "application_key_issued")
            )
            == expected
        )
