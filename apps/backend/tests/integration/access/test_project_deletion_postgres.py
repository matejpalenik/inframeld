"""Exercise authentic atomic Project-deletion admission, not effects-layer preconditions."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from typing import override
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import Connection, delete, event, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapper
from tests.integration.access.test_project_application_shutdown_postgres import wait_for_blocker
from tests.support.application_account_scenarios import create_account
from tests.support.application_key_scenarios import store_application_key
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_creation_scenarios import create_project
from tests.support.project_upload_default_scenarios import (
    UploadDefaultScenario,
    replace_upload_default,
    seed_upload_default_scenario,
    upload_default_effects,
    upload_default_service,
)

from inframeld_backend.access.application.commands.delete_project_command import (
    DeleteProjectCommand,
)
from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
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
from inframeld_backend.access.application.dtos.project_deletion_facts_dto import (
    ProjectDeletionFactsDTO,
)
from inframeld_backend.access.application.dtos.project_deletion_result_dto import (
    ProjectDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_record_dto import (
    ProjectUploadDefaultRecordDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.queries.get_project_upload_default_query import (
    GetProjectUploadDefaultQuery,
)
from inframeld_backend.access.application.services.application_authentication_service import (
    ApplicationAuthenticationService,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.services.deletion_status_authorization_service import (
    DeletionStatusAuthorizationService,
)
from inframeld_backend.access.application.services.project_deletion_fingerprint_service import (
    ProjectDeletionFingerprintService,
)
from inframeld_backend.access.application.services.project_deletion_service import (
    ProjectDeletionService,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.entities.project_upload_default import ProjectUploadDefault
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_application_authentication_facts_reader import (
    PostgresApplicationAuthenticationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_deletion_status_facts_reader import (
    PostgresDeletionStatusFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_deletion_facts_reader import (
    PostgresProjectDeletionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_deletion_result_reader import (
    PostgresProjectDeletionResultReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_upload_default_repository import (
    PostgresProjectUploadDefaultRepository,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
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
from inframeld_backend.access.infrastructure.writers.postgres_project_deletion_admission_writer import (
    PostgresProjectDeletionAdmissionWriter,
)
from inframeld_backend.bootstrap.application_key_composition import open_application_key_issuance
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.job_errors import JobQueueFullError
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.services.deletion_status_read_service import (
    DeletionStatusReadService,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.infrastructure.readers.postgres_deletion_status_reader import (
    PostgresDeletionStatusReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

HTTP_PROFILE = ApplicationKeyVerificationProfileDTO(
    ApplicationKeyAudience("https://api.test"), ApplicationKeyAdapter.HTTP
)


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


@dataclass(frozen=True, slots=True)
class DeletionScenario:
    defaults: UploadDefaultScenario
    account: CreatedApplicationAccountDTO
    credential: ApplicationKeyCredential
    revision: int
    other_project: ProjectId


async def seed_deletion_scenario(database: Database) -> DeletionScenario:
    defaults = await seed_upload_default_scenario(database)
    account = (
        await create_account(
            database, defaults.actor.access, defaults.project_id, revision=defaults.revision
        )
    ).account
    credential = await store_application_key(
        database,
        principal_id=account.principal_id,
        organization_id=account.organization_id,
        project_id=account.project_id,
    )
    changed = await replace_upload_default(database, defaults, (0,), account.access_revision)
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == defaults.actor.organization_id.value
            )
        )
    assert revision is not None
    other = await create_project(
        database,
        replace(defaults.actor, access_revision=revision),
        name="unrelated",
        key="unrelated-project",
    )
    return DeletionScenario(
        defaults, account, credential, changed.default.access_revision, other.project.project_id
    )


@pytest_asyncio.fixture
async def deletion_scope(database: Database) -> DeletionScenario:
    return await seed_deletion_scenario(database)


def deletion_context(project_id: ProjectId, key: str = "delete-original") -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        HttpMethod.DELETE, f"/v1/projects/{project_id.value}", IdempotencyKey(key)
    )


def deletion_service(
    session: AsyncSession,
    *,
    capacity: int = 8,
    transaction_manager: TransactionManager | None = None,
) -> ProjectDeletionService:
    return ProjectDeletionService(
        transaction_manager=SqlAlchemyTransactionManager(session)
        if transaction_manager is None
        else transaction_manager,
        project_deletion_facts_reader=PostgresProjectDeletionFactsReader(session),
        project_deletion_admission_writer=PostgresProjectDeletionAdmissionWriter(
            session, capacity=capacity
        ),
        project_deletion_result_reader=PostgresProjectDeletionResultReader(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        project_deletion_fingerprint_service=ProjectDeletionFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"D" * 32))
        ),
    )


async def admit_deletion(
    database: Database,
    scope: DeletionScenario,
    *,
    key: str = "delete-original",
    revision: int | None = None,
    capacity: int = 8,
) -> ProjectDeletionResultDTO:
    async with database.session() as session:
        return await deletion_service(session, capacity=capacity).delete(
            access=scope.defaults.actor.access,
            command=DeleteProjectCommand(
                scope.defaults.project_id, scope.revision if revision is None else revision
            ),
            context=deletion_context(scope.defaults.project_id, key),
            request_id=RequestId(uuid4()),
        )


async def assert_atomic_original(
    database: Database, scope: DeletionScenario, result: ProjectDeletionResultDTO
) -> None:
    async with database.session() as session:
        project = await session.get(ProjectRow, scope.defaults.project_id.value)
        parent = await session.get(ProjectDeletionObligationRow, result.obligation_id.value)
        job = await session.get(DurableJobRow, result.job_id.value)
        original = await session.get(IdempotencyReservationRow, result.operation.operation_id.value)
        retained = await session.get(DeletionStatusBindingRow, result.operation.operation_id.value)
        assert (
            project is not None
            and parent is not None
            and job is not None
            and original is not None
            and retained is not None
        )
        assert project.status is ProjectStatus.DELETING
        assert project.access_revision == scope.revision + 1
        assert (
            parent.operation_id,
            parent.job_id,
            parent.project_id,
            parent.organization_id,
            parent.initiator_principal_id,
        ) == (
            result.operation.operation_id.value,
            result.job_id.value,
            scope.defaults.project_id.value,
            scope.defaults.actor.organization_id.value,
            scope.defaults.actor.access.actor_principal_id.value,
        )
        assert (parent.before_access_revision, parent.access_revision) == (
            scope.revision,
            scope.revision + 1,
        )
        assert parent.shutdown_completed_at is None and parent.physical_cleanup_completed_at is None
        assert (
            job.binding_kind,
            job.deletion_obligation_id,
            job.cleanup_obligation_id,
            job.operation_id,
        ) == ("project_deletion", parent.id, None, None)
        assert (job.payload_kind, job.payload_version, job.payload) == (
            "project.application-shutdown",
            1,
            parent.id.bytes,
        )
        assert job.status == "queued" and job.attempt_count == 0
        assert (
            original.state is OperationReservationState.REPLAYABLE and original.expires_at is None
        )
        assert result.operation.expires_at is None
        assert (
            retained.authority_family,
            retained.action_id,
            retained.method,
            retained.requested_route,
        ) == (
            "project_action_use",
            "delete-project",
            "DELETE",
            f"/v1/projects/{scope.defaults.project_id.value}",
        )
        assert (retained.request_key, retained.request_fingerprint) == (
            parent.request_key,
            parent.request_fingerprint,
        )
        events = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == result.operation.operation_id.value
                )
            )
        ).all()
        assert len(events) == 1
        assert events[0].event_type == "project_deletion_admitted"
        assert events[0].actor_principal_id == scope.defaults.actor.access.actor_principal_id.value
        outside = await session.get(ProjectRow, scope.other_project.value)
        assert outside is not None and outside.status is ProjectStatus.ACTIVE
        assert set(
            await session.scalars(
                select(AccessGroupRow.id).where(
                    AccessGroupRow.project_id == scope.defaults.project_id.value
                )
            )
        ) == {g.group_id.value for g in scope.defaults.groups}
        credential = await session.get(ApplicationKeyRow, scope.credential.key_id.value)
        assert credential is not None and credential.revoked_at is None


async def test_atomic_admission_blocks_and_retains_original(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    result = await admit_deletion(database, deletion_scope)
    assert result.operation.created
    await assert_atomic_original(database, deletion_scope, result)


async def test_original_replay_precedes_fresh_revision_and_does_not_readmit(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    first = await admit_deletion(database, deletion_scope)
    replay = await admit_deletion(database, deletion_scope)
    assert not replay.operation.created
    assert replace(replay, operation=first.operation) == first
    await assert_atomic_original(database, deletion_scope, first)


async def test_current_delete_grant_is_required_before_original_replay(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    first = await admit_deletion(database, deletion_scope)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == deletion_scope.defaults.project_id.value,
                ProjectActionGrantRow.recipient_principal_id
                == deletion_scope.defaults.actor.access.actor_principal_id.value,
                ProjectActionGrantRow.action == "delete-project",
            )
        )
    with pytest.raises(AccessDeniedError):
        await admit_deletion(database, deletion_scope)
    async with database.session() as session:
        assert (
            await session.get(ProjectDeletionObligationRow, first.obligation_id.value) is not None
        )
        assert (
            await session.scalar(select(func.count()).select_from(ProjectDeletionObligationRow))
            == 1
        )


async def test_fresh_stale_revision_does_not_block_or_reserve(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    with pytest.raises(StaleRevisionError):
        await admit_deletion(database, deletion_scope, revision=deletion_scope.revision - 1)
    async with database.session() as session:
        project = await session.get(ProjectRow, deletion_scope.defaults.project_id.value)
        assert project is not None and project.status is ProjectStatus.ACTIVE
        assert project.access_revision == deletion_scope.revision
        assert list(await session.scalars(select(ProjectDeletionObligationRow.id))) == []


async def test_capacity_denial_rolls_back_block_revision_original_and_audit(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    async with database.session() as session:
        await deletion_service(session, capacity=1).delete(
            access=deletion_scope.defaults.actor.access,
            command=DeleteProjectCommand(deletion_scope.other_project, 1),
            context=deletion_context(deletion_scope.other_project, "occupy"),
            request_id=RequestId(uuid4()),
        )
    with pytest.raises(JobQueueFullError):
        await admit_deletion(database, deletion_scope, capacity=1)
    async with database.session() as session:
        project = await session.get(ProjectRow, deletion_scope.defaults.project_id.value)
        assert project is not None and (project.status, project.access_revision) == (
            ProjectStatus.ACTIVE,
            deletion_scope.revision,
        )
        assert (
            list(
                await session.scalars(
                    select(ProjectDeletionObligationRow.id).where(
                        ProjectDeletionObligationRow.project_id == project.id
                    )
                )
            )
            == []
        )
        assert (
            list(
                await session.scalars(
                    select(IdempotencyReservationRow.operation_id).where(
                        IdempotencyReservationRow.project_id == project.id,
                        IdempotencyReservationRow.method == "DELETE",
                    )
                )
            )
            == []
        )
        assert (
            list(
                await session.scalars(
                    select(AccessAuditEventRow.id).where(
                        AccessAuditEventRow.project_id == project.id,
                        AccessAuditEventRow.event_type == "project_deletion_admitted",
                    )
                )
            )
            == []
        )


@pytest.mark.parametrize("failure", ["before-commit", "cancel", "lost-commit-ack"])
async def test_transaction_failure_preserves_rollback_or_exact_original(
    database: Database, deletion_scope: DeletionScenario, failure: str
) -> None:
    class InterruptedTransaction(SqlAlchemyTransactionManager):
        @override
        @asynccontextmanager
        async def begin(self) -> AsyncGenerator[None]:
            async with super().begin():
                yield
                if failure == "before-commit":
                    raise ConnectionError("controlled failure before commit")
                if failure == "cancel":
                    raise asyncio.CancelledError()
            if failure == "lost-commit-ack":
                raise ConnectionError("controlled lost commit acknowledgment")

    async with database.session() as session:
        with pytest.raises(asyncio.CancelledError if failure == "cancel" else ConnectionError):
            await deletion_service(
                session, transaction_manager=InterruptedTransaction(session)
            ).delete(
                access=deletion_scope.defaults.actor.access,
                command=DeleteProjectCommand(
                    deletion_scope.defaults.project_id, deletion_scope.revision
                ),
                context=deletion_context(deletion_scope.defaults.project_id),
                request_id=RequestId(uuid4()),
            )
    if failure == "lost-commit-ack":
        replay = await admit_deletion(database, deletion_scope)
        assert not replay.operation.created
        await assert_atomic_original(database, deletion_scope, replay)
    else:
        async with database.session() as session:
            project = await session.get(ProjectRow, deletion_scope.defaults.project_id.value)
            assert project is not None and (project.status, project.access_revision) == (
                ProjectStatus.ACTIVE,
                deletion_scope.revision,
            )
            assert list(await session.scalars(select(ProjectDeletionObligationRow.id))) == []
            assert (
                list(
                    await session.scalars(
                        select(IdempotencyReservationRow.operation_id).where(
                            IdempotencyReservationRow.method == "DELETE"
                        )
                    )
                )
                == []
            )
            assert (
                list(
                    await session.scalars(
                        select(AccessAuditEventRow.id).where(
                            AccessAuditEventRow.event_type == "project_deletion_admitted"
                        )
                    )
                )
                == []
            )


@pytest.mark.parametrize("read", [True, False], ids=["GET", "PUT"])
async def test_blocked_project_rejects_current_access_default_operations(
    database: Database, deletion_scope: DeletionScenario, read: bool
) -> None:
    await admit_deletion(database, deletion_scope)
    with pytest.raises(ResourceNotFoundError):
        if read:
            async with database.session() as session:
                await upload_default_service(session).get(
                    access=deletion_scope.defaults.actor.access,
                    query=GetProjectUploadDefaultQuery(deletion_scope.defaults.project_id),
                )
        else:
            await replace_upload_default(
                database, deletion_scope.defaults, (1,), deletion_scope.revision + 1, "blocked-put"
            )


async def test_default_write_before_block_preserves_live_links_and_original_history(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    changed = await replace_upload_default(
        database, deletion_scope.defaults, (1,), deletion_scope.revision, "default-before-delete"
    )
    before = await upload_default_effects(database, deletion_scope.defaults.project_id)
    await admit_deletion(database, deletion_scope, revision=changed.default.access_revision)
    after = await upload_default_effects(database, deletion_scope.defaults.project_id)
    assert after[0] == before[0] and after[2:] == before[2:]
    assert after[1] == changed.default.access_revision + 1


async def test_postblock_status_uses_current_human_and_original_initiator(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    async with database.session() as session, session.begin():
        status = await DeletionStatusReadService(
            DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
            PostgresDeletionStatusReader(session),
        ).lookup(
            access=deletion_scope.defaults.actor.access,
            query=GetDeletionStatusQuery(accepted.operation.operation_id),
        )
    assert isinstance(status, RetainedDeletionStatusDTO)
    assert status.admission_confirmed is True and status.access_blocked is True
    assert (
        status.application_shutdown_complete is False and status.physical_cleanup_complete is False
    )
    assert status.expires_at is None


async def settle_race(tasks: tuple[asyncio.Task[None], ...], primary: BaseException | None) -> None:
    """Reap these two owned operations within the existing three-second test cleanup bound."""
    errors: list[BaseException] = []
    try:
        for task in tasks:
            if not task.done():
                task.cancel()
        async with asyncio.timeout(3):
            outcomes = await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
        for outcome in outcomes:
            if (
                isinstance(outcome, BaseException)
                and not isinstance(outcome, asyncio.CancelledError)
                and outcome is not primary
            ):
                errors.append(outcome)
    except BaseException as error:
        if error is not primary:
            errors.append(error)
    if errors:
        raise BaseExceptionGroup(
            "Project-deletion ordering work and task settlement failed",
            ([primary] if primary is not None else []) + errors,
        ) from None


@pytest.mark.parametrize("deletion_first", [False, True], ids=["issuance-wins", "deletion-wins"])
async def test_real_key_issuance_and_deletion_share_current_project_coordination(
    database: Database,
    deletion_scope: DeletionScenario,
    monkeypatch: pytest.MonkeyPatch,
    deletion_first: bool,
) -> None:
    deletion_request = replace(
        deletion_scope, revision=deletion_scope.revision + int(not deletion_first)
    )
    entered, release = asyncio.Event(), asyncio.Event()
    issued: list[ApplicationKeyIssueResultDTO] = []
    accepted: list[ProjectDeletionResultDTO] = []
    original_create = PostgresApplicationKeyIssuanceWriter.create
    original_lock = PostgresProjectDeletionFactsReader.lock_for_deletion

    async def hold_key(
        writer: PostgresApplicationKeyIssuanceWriter,
        *,
        key: ApplicationKeyCreationDTO,
        expected_project_revision: int,
    ) -> None:
        await original_create(writer, key=key, expected_project_revision=expected_project_revision)
        entered.set()
        await release.wait()

    async def hold_deletion(
        reader: PostgresProjectDeletionFactsReader,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
    ) -> ProjectDeletionFactsDTO | None:
        result = await original_lock(reader, access=access, project_id=project_id)
        entered.set()
        await release.wait()
        return result

    monkeypatch.setattr(
        PostgresProjectDeletionFactsReader, "lock_for_deletion", hold_deletion
    ) if deletion_first else monkeypatch.setattr(
        PostgresApplicationKeyIssuanceWriter, "create", hold_key
    )

    async def issue() -> None:
        async def execute() -> ApplicationKeyIssueResultDTO:
            async with open_application_key_issuance(
                database,
                ApplicationKeyIssuanceFingerprintService(
                    RequestFingerprintService(RequestFingerprintKey(b"I" * 32))
                ),
                http_profile=HTTP_PROFILE,
                mcp_profile=None,
                settings=ApplicationKeyIssuanceSettings(),
            ) as issuer:
                account = deletion_scope.account
                return await issuer.issue(
                    access=deletion_scope.defaults.actor.access,
                    command=IssueApplicationKeyCommand(
                        account.project_id,
                        account.principal_id,
                        (ApplicationKeyAdapter.HTTP,),
                        deletion_scope.revision,
                    ),
                    context=IdempotencyContextDTO(
                        HttpMethod.POST,
                        f"/v1/projects/{account.project_id.value}/application-accounts/{account.principal_id.value}/keys",
                        IdempotencyKey("racing-key"),
                    ),
                )

        if deletion_first:
            with pytest.raises(ResourceNotFoundError):
                await execute()
        else:
            issued.append(await execute())

    async def block() -> None:
        accepted.append(await admit_deletion(database, deletion_request))

    first: asyncio.Task[None] | None = None
    second: asyncio.Task[None] | None = None
    primary: BaseException | None = None
    try:
        first = asyncio.create_task(block() if deletion_first else issue())
        async with asyncio.timeout(3):
            await entered.wait()
        second = asyncio.create_task(issue() if deletion_first else block())
        await wait_for_blocker(database)
        release.set()
        async with asyncio.timeout(3):
            await asyncio.shield(asyncio.gather(first, second))
    except BaseException as error:
        primary = error
        raise
    finally:
        release.set()
        await settle_race(tuple(task for task in (first, second) if task is not None), primary)
    assert len(accepted) == 1
    if deletion_first:
        assert issued == []
    else:
        assert len(issued) == 1
        credential = issued[0].credential
        assert credential is not None
        verifier = PostgresApplicationKeyVerifier(database)
        verified = await verifier.verify(credential, profile=HTTP_PROFILE)
        assert verified is not None
        assert verified.principal_id == deletion_scope.account.principal_id
        facts_reader = PostgresApplicationAuthenticationFactsReader(database)
        facts = await facts_reader.read(verified.principal_id)
        assert facts is not None
        assert facts.principal.id == deletion_scope.account.principal_id
        assert facts.principal.organization_id == deletion_scope.account.organization_id
        assert facts.principal.kind is PrincipalKind.APPLICATION
        assert facts.principal.status is PrincipalStatus.ACTIVE
        assert facts.project_id == deletion_scope.account.project_id
        assert facts.is_project_member and facts.has_coherent_binding
        assert facts.project_status is ProjectStatus.DELETING
        with pytest.raises(AccessDeniedError):
            await ApplicationAuthenticationService(
                key_verifier=verifier,
                authentication_facts_reader=facts_reader,
                verification_profile=HTTP_PROFILE,
            ).authenticate(credential)
    await assert_atomic_original(database, deletion_request, accepted[0])


@pytest.mark.parametrize("deletion_first", [False, True], ids=["default-wins", "deletion-wins"])
async def test_default_write_and_deletion_serialize_and_preserve_actual0030_references(
    database: Database,
    deletion_scope: DeletionScenario,
    monkeypatch: pytest.MonkeyPatch,
    deletion_first: bool,
) -> None:
    entered, release = asyncio.Event(), asyncio.Event()
    original_save = PostgresProjectUploadDefaultRepository.save
    original_lock = PostgresProjectDeletionFactsReader.lock_for_deletion

    async def hold_default(
        repository: PostgresProjectUploadDefaultRepository,
        default: ProjectUploadDefault,
        *,
        original: ProjectUploadDefaultRecordDTO,
        fingerprint: RequestFingerprint,
    ) -> None:
        await original_save(repository, default, original=original, fingerprint=fingerprint)
        entered.set()
        await release.wait()

    async def hold_deletion(
        reader: PostgresProjectDeletionFactsReader,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
    ) -> ProjectDeletionFactsDTO | None:
        result = await original_lock(reader, access=access, project_id=project_id)
        entered.set()
        await release.wait()
        return result

    if deletion_first:
        monkeypatch.setattr(PostgresProjectDeletionFactsReader, "lock_for_deletion", hold_deletion)
    else:
        monkeypatch.setattr(PostgresProjectUploadDefaultRepository, "save", hold_default)

    async def write_default() -> None:
        if deletion_first:
            with pytest.raises(ResourceNotFoundError):
                await replace_upload_default(
                    database,
                    deletion_scope.defaults,
                    (1,),
                    deletion_scope.revision,
                    "racing-default",
                )
        else:
            await replace_upload_default(
                database, deletion_scope.defaults, (1,), deletion_scope.revision, "racing-default"
            )

    async def block() -> None:
        await admit_deletion(
            database, deletion_scope, revision=deletion_scope.revision + int(not deletion_first)
        )

    first: asyncio.Task[None] | None = None
    second: asyncio.Task[None] | None = None
    primary: BaseException | None = None
    try:
        first = asyncio.create_task(block() if deletion_first else write_default())
        async with asyncio.timeout(3):
            await entered.wait()
        second = asyncio.create_task(write_default() if deletion_first else block())
        await wait_for_blocker(database)
        release.set()
        async with asyncio.timeout(3):
            await asyncio.shield(asyncio.gather(first, second))
    except BaseException as error:
        primary = error
        raise
    finally:
        release.set()
        await settle_race(tuple(task for task in (first, second) if task is not None), primary)
    effects = await upload_default_effects(database, deletion_scope.defaults.project_id)
    assert effects[0] == (
        deletion_scope.defaults.groups[0 if deletion_first else 1].group_id.value,
    )
    assert effects[3] == 1 + int(not deletion_first)
    async with database.session() as session:
        assert set(
            await session.scalars(
                select(AccessGroupRow.id).where(
                    AccessGroupRow.project_id == deletion_scope.defaults.project_id.value
                )
            )
        ) == {g.group_id.value for g in deletion_scope.defaults.groups}


async def test_required_admission_audit_failure_rolls_back_the_entire_acceptance(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    def reject_audit(
        mapper: Mapper[AccessAuditEventRow], connection: Connection, target: AccessAuditEventRow
    ) -> None:
        if target.event_type == "project_deletion_admitted":
            raise ConnectionError("controlled required audit failure")

    event.listen(AccessAuditEventRow, "before_insert", reject_audit)
    try:
        with pytest.raises(ConnectionError):
            await admit_deletion(database, deletion_scope)
    finally:
        event.remove(AccessAuditEventRow, "before_insert", reject_audit)
    async with database.session() as session:
        project = await session.get(ProjectRow, deletion_scope.defaults.project_id.value)
        assert project is not None and (project.status, project.access_revision) == (
            ProjectStatus.ACTIVE,
            deletion_scope.revision,
        )
        assert list(await session.scalars(select(ProjectDeletionObligationRow.id))) == []
        assert (
            list(
                await session.scalars(
                    select(IdempotencyReservationRow.operation_id).where(
                        IdempotencyReservationRow.method == "DELETE"
                    )
                )
            )
            == []
        )
        assert (
            list(
                await session.scalars(
                    select(AccessAuditEventRow.id).where(
                        AccessAuditEventRow.event_type == "project_deletion_admitted"
                    )
                )
            )
            == []
        )


async def test_eligible_original_status_survives_lost_membership_but_ordinary_replay_does_not(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    async with database.session() as session, session.begin():
        actor = deletion_scope.defaults.actor.access.actor_principal_id.value
        # This controlled disappearance exercises status authority, not shutdown effects.
        await session.execute(
            delete(GroupActionGrantRow).where(
                GroupActionGrantRow.project_id == deletion_scope.defaults.project_id.value,
                GroupActionGrantRow.recipient_principal_id == actor,
            )
        )
        await session.execute(
            delete(GroupManagerRow).where(
                GroupManagerRow.project_id == deletion_scope.defaults.project_id.value,
                GroupManagerRow.principal_id == actor,
            )
        )
        await session.execute(
            delete(GroupMembershipRow).where(
                GroupMembershipRow.project_id == deletion_scope.defaults.project_id.value,
                GroupMembershipRow.principal_id == actor,
            )
        )
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == deletion_scope.defaults.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == actor,
            )
        )
        await session.execute(
            delete(ApplicationActionGrantRow).where(
                ApplicationActionGrantRow.project_id == deletion_scope.defaults.project_id.value,
                ApplicationActionGrantRow.recipient_principal_id == actor,
                ApplicationActionGrantRow.recipient_kind == PrincipalKind.HUMAN,
            )
        )
        await session.execute(
            delete(ProjectMembershipRow).where(
                ProjectMembershipRow.project_id == deletion_scope.defaults.project_id.value,
                ProjectMembershipRow.principal_id == actor,
            )
        )
    with pytest.raises(ResourceNotFoundError):
        await admit_deletion(database, deletion_scope)
    async with database.session() as session, session.begin():
        retained = await DeletionStatusReadService(
            DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
            PostgresDeletionStatusReader(session),
        ).lookup(
            access=deletion_scope.defaults.actor.access,
            query=GetDeletionStatusQuery(accepted.operation.operation_id),
        )
    assert isinstance(retained, RetainedDeletionStatusDTO)
    assert retained.access_blocked is True and retained.expires_at is None


async def test_another_eligible_human_cannot_observe_original_initiator_status(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    async with database.session() as session:
        identity = await session.scalar(
            select(HumanIdentityLinkRow).where(
                HumanIdentityLinkRow.principal_id == deletion_scope.defaults.bob_id.value
            )
        )
    assert identity is not None
    other = AccessContextDTO(
        deletion_scope.defaults.bob_id,
        MockAuthenticationEvidence.browser(
            VerifiedHumanIdentityDTO(
                IdentityAuthority(identity.authority), IdentitySubject(identity.subject)
            )
        ),
    )
    async with database.session() as session, session.begin():
        result = await DeletionStatusReadService(
            DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
            PostgresDeletionStatusReader(session),
        ).lookup(access=other, query=GetDeletionStatusQuery(accepted.operation.operation_id))
    assert isinstance(result, UnresolvedOperationDTO)


async def test_inactive_original_human_cannot_use_content_free_status(
    database: Database, deletion_scope: DeletionScenario
) -> None:
    accepted = await admit_deletion(database, deletion_scope)
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == deletion_scope.defaults.actor.access.actor_principal_id.value)
            .values(status=PrincipalStatus.RETIRED)
        )
    async with database.session() as session, session.begin():
        with pytest.raises(AccessDeniedError):
            await DeletionStatusReadService(
                DeletionStatusAuthorizationService(PostgresDeletionStatusFactsReader(session)),
                PostgresDeletionStatusReader(session),
            ).lookup(
                access=deletion_scope.defaults.actor.access,
                query=GetDeletionStatusQuery(accepted.operation.operation_id),
            )
