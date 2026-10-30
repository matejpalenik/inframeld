"""Prove queue admission and attempt ownership against real PostgreSQL."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from typing import override
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.application_worker_process import (
    application_worker_command,
    application_worker_process,
)
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobQueueFullError,
    JobStoppedError,
    UnsupportedJobPayloadError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.services.job_checkpoint_service import (
    JobCheckpointService,
)
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


async def _request(
    database: Database,
) -> tuple[OperationReservationRequestDTO, AdmittedWorkAuthorityDTO]:
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_kind=PrincipalKind.APPLICATION,
        )
        await session.execute(
            update(ProjectActionGrantRow)
            .where(
                ProjectActionGrantRow.project_id == scenario.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == scenario.principal_id.value,
            )
            .values(action="create-sources")
        )
        organization = await session.scalar(
            select(ProjectRow.organization_id).where(ProjectRow.id == scenario.project_id.value)
        )
        installation = await session.scalar(select(InstallationIdentityRow.installation_id))
        assert organization is not None and installation is not None
    authority = AdmittedWorkAuthorityDTO(
        scenario.principal_id,
        PrincipalKind.APPLICATION,
        InstallationId(installation),
        OrganizationId(organization),
        scenario.project_id,
        ActionId("create-sources"),
        None,
    )
    request = OperationReservationRequestDTO(
        principal_id=scenario.principal_id,
        organization_id=authority.organization_id,
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/sources",
        key=IdempotencyKey("job-1"),
        fingerprint=b"F" * 32,
    )
    return request, authority


@pytest.mark.asyncio
async def test_concurrent_admissions_cannot_both_take_final_queue_slot(database: Database) -> None:
    request, authority = await _request(database)
    barrier = asyncio.Barrier(2)

    async def admit(key: str) -> bool:
        try:
            async with database.session() as session, session.begin():
                reservation = await PostgresOperationReservationWriter(session).reserve(
                    replace(request, key=IdempotencyKey(key))
                )
                await barrier.wait()
                await PostgresJobStore(session).admit(
                    operation_id=reservation.operation_id,
                    request_id=RequestId(uuid4()),
                    authority=authority,
                    payload=JobPayload("test.progress", 1, b"fixed"),
                    capacity=1,
                )
                return True
        except JobQueueFullError:
            return False

    assert sorted(await asyncio.gather(admit("first"), admit("second"))) == [False, True]


async def _admit(
    database: Database, *, kind: str = "test.progress", version: int = 1, data: bytes = b"fixed"
) -> JobAdmissionDTO:
    request, authority = await _request(database)
    async with database.session() as session, session.begin():
        writer = PostgresOperationReservationWriter(session)
        operation = await writer.reserve(request)
        result = await PostgresJobStore(session).admit(
            operation_id=operation.operation_id,
            request_id=RequestId(uuid4()),
            authority=authority,
            payload=JobPayload(kind, version, data),
            capacity=8,
        )
        await writer.mark_replayable(operation.operation_id, OperationReplayKind.ASYNC_JOB)
    return result


async def _claim(database: Database) -> JobAttemptContextDTO | None:
    async with database.session() as session:
        return await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("test.progress", 1),),
            worker_id=uuid4(),
        ).claim_next()


@pytest.mark.asyncio
async def test_replacement_fence_rejects_late_progress_and_completion(database: Database) -> None:
    admitted = await _admit(database)
    first = await _claim(database)
    assert first is not None
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == admitted.job_id.value)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    await _claim(database)
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == admitted.job_id.value)
            .values(due_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    second = await _claim(database)
    assert second is not None and second.job_id == first.job_id and second.fence != first.fence
    async with database.session() as session, session.begin():
        with pytest.raises(JobFenceLostError):
            await PostgresJobStore(session).checkpoint(first, b"late", lease_seconds=30)
    async with database.session() as session, session.begin():
        with pytest.raises(JobFenceLostError):
            await PostgresJobStore(session).finish(first, status=JobStatus.SUCCEEDED, reason=None)
    async with database.session() as session, session.begin():
        store = PostgresJobStore(session)
        await store.checkpoint(second, b"replacement", lease_seconds=30)
        await store.finish(second, status=JobStatus.SUCCEEDED, reason=None)
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admitted.operation_id)
        assert (
            saved is not None
            and saved.checkpoint == b"replacement"
            and saved.status is JobStatus.SUCCEEDED
        )
        reservation = await session.scalar(
            select(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == admitted.operation_id.value
            )
        )
        assert (
            reservation is not None
            and reservation.replay_kind is OperationReplayKind.ASYNC_JOB
            and reservation.expires_at is not None
        )


@pytest.mark.asyncio
async def test_unknown_effect_survives_restart_without_another_attempt(database: Database) -> None:
    admitted = await _admit(database)
    first = await _claim(database)
    assert first is not None
    async with database.session() as session, session.begin():
        await PostgresJobStore(session).begin_effect(first, "paid-unit-1")
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == admitted.job_id.value)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    assert await _claim(database) is None
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admitted.operation_id)
    assert (
        saved is not None
        and saved.status is JobStatus.RECOVERY_REQUIRED
        and saved.attempt == 1
        and saved.pending_effect == "paid-unit-1"
    )


@pytest.mark.asyncio
async def test_unsupported_persisted_payload_is_failed_without_execution(
    database: Database,
) -> None:
    admitted = await _admit(database, version=2)
    assert await _claim(database) is None
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admitted.operation_id)
    assert (
        saved is not None
        and saved.status is JobStatus.FAILED
        and saved.reason == "unsupported_payload"
        and saved.attempt == 0
    )


@pytest.mark.asyncio
async def test_cancellation_needs_no_new_queue_slot(database: Database) -> None:
    admitted = await _admit(database)
    async with database.session() as session, session.begin():
        await PostgresJobStore(session).request_cancel(admitted.job_id)
    assert await _claim(database) is None
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admitted.operation_id)
    assert saved is not None and saved.status is JobStatus.CANCELED


@pytest.mark.asyncio
async def test_lost_admission_response_recovers_original_job_request_and_one_audit(
    database: Database,
) -> None:
    request, authority = await _request(database)
    original_request = RequestId(uuid4())

    async def admit(request_id: RequestId) -> JobAdmissionDTO:
        async with database.session() as session, session.begin():
            service = JobAdmissionService(
                ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
                AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
                IdempotencyService(PostgresOperationReservationWriter(session)),
                PostgresJobStore(session),
                PostgresJobAdmissionAuditWriter(session),
                supported_payloads=(("test.progress", 1),),
            )
            return await service.admit(
                access=AccessContextDTO(
                    authority.principal_id, MockAuthenticationEvidence.application_key()
                ),
                authority=authority,
                context=OperationAdmissionContextDTO(
                    request.method, request.requested_route, request.key
                ),
                fingerprint=RequestFingerprint(request.fingerprint),
                request_id=request_id,
                payload=JobPayload("test.progress", 1, b"fixed"),
            )

    first = await admit(original_request)
    retry = await admit(RequestId(uuid4()))
    assert (
        retry.job_id == first.job_id
        and retry.operation_id == first.operation_id
        and first.created
        and not retry.created
    )
    async with database.session() as session:
        job = await session.scalar(
            select(DurableJobRow).where(DurableJobRow.id == first.job_id.value)
        )
        audits = tuple(
            (
                await session.scalars(
                    select(AccessAuditEventRow).where(
                        AccessAuditEventRow.correlation_id == first.operation_id.value
                    )
                )
            ).all()
        )
    assert job is not None and job.request_id == original_request.value
    assert len(audits) == 1 and audits[0].event_type == "job_admitted"


@pytest.mark.asyncio
async def test_current_principal_suspension_blocks_admitted_work(database: Database) -> None:
    _, authority = await _request(database)
    async with database.session() as session, session.begin():
        service = AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session))
        await service.require_current(authority)
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == authority.principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
        with pytest.raises(AccessDeniedError):
            await service.require_current(authority)


async def _checkpoints(database: Database, context: JobAttemptContextDTO, data: bytes) -> None:
    async with database.session() as session:
        await JobCheckpointService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
        ).save(context, data)


@pytest.mark.asyncio
async def test_authority_loss_commits_stop_without_publishing_late_checkpoint(
    database: Database,
) -> None:
    admitted = await _admit(database)
    context = await _claim(database)
    assert context is not None
    await _checkpoints(database, context, b"confirmed-first-unit")
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == context.authority.principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    with pytest.raises(JobStoppedError):
        await _checkpoints(database, context, b"forbidden-later-unit")
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admitted.operation_id)
    assert (
        saved is not None
        and saved.status is JobStatus.FAILED
        and saved.reason == "authority_changed"
        and saved.checkpoint == b"confirmed-first-unit"
    )
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == context.authority.principal_id.value)
            .values(status=PrincipalStatus.ACTIVE)
        )
    assert await _claim(database) is None


@pytest.mark.asyncio
async def test_authority_loss_after_dispatch_preserves_uncertainty(database: Database) -> None:
    admitted = await _admit(database)
    context = await _claim(database)
    assert context is not None
    async with database.session() as session:
        operations = JobCheckpointService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
        )
        await operations.begin_effect(context, "original-paid-unit")
    async with database.session() as session, session.begin():
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == context.authority.principal_id.value)
            .values(status=PrincipalStatus.SUSPENDED)
        )
    with pytest.raises(JobStoppedError):
        await _checkpoints(database, context, b"late-protected-result")
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admitted.operation_id)
    assert (
        saved is not None
        and saved.status is JobStatus.RECOVERY_REQUIRED
        and saved.pending_effect == "original-paid-unit"
        and saved.checkpoint == b""
    )


@pytest.mark.asyncio
async def test_competing_worker_processes_cannot_claim_two_active_attempts(
    database: Database,
) -> None:
    first = await _admit(database)
    await _admit(database)
    claims = await asyncio.gather(_claim(database), _claim(database))
    active = [claim for claim in claims if claim is not None]
    assert len(active) == 1 and active[0].job_id == first.job_id


@pytest.mark.asyncio
async def test_attempt_exhaustion_retains_confirmed_progress_and_original_job(
    database: Database,
) -> None:
    admitted = await _admit(database)
    for attempt in range(1, 4):
        context = await _claim(database)
        assert (
            context is not None and context.job_id == admitted.job_id and context.attempt == attempt
        )
        assert context.checkpoint == (b"" if attempt == 1 else str(attempt - 1).encode())
        async with database.session() as session, session.begin():
            await PostgresJobStore(session).checkpoint(
                context, str(attempt).encode(), lease_seconds=30
            )
            await session.execute(
                update(DurableJobRow)
                .where(DurableJobRow.id == admitted.job_id.value)
                .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
            )
        assert await _claim(database) is None
        async with database.session() as session, session.begin():
            await session.execute(
                update(DurableJobRow)
                .where(DurableJobRow.id == admitted.job_id.value)
                .values(due_at=func.clock_timestamp() - timedelta(seconds=1))
            )
    assert await _claim(database) is None
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admitted.operation_id)
    assert (
        saved is not None
        and saved.status is JobStatus.FAILED
        and saved.attempt == 3
        and saved.checkpoint == b"3"
    )


@pytest.mark.asyncio
async def test_queue_wait_deadline_gives_explicit_terminal_outcome(database: Database) -> None:
    admitted = await _admit(database)
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == admitted.job_id.value)
            .values(queued_deadline=func.clock_timestamp() - timedelta(seconds=1))
        )
    assert await _claim(database) is None
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admitted.operation_id)
    assert (
        saved is not None
        and saved.status is JobStatus.FAILED
        and saved.reason == "queue_wait_exhausted"
        and saved.attempt == 0
    )


class MockFailingJobAdmissionAuditWriter(PostgresJobAdmissionAuditWriter):
    @override
    async def append(
        self,
        admission: JobAdmissionDTO,
        *,
        request_id: RequestId,
        authority: AdmittedWorkAuthorityDTO,
        payload: JobPayload,
    ) -> None:
        await super().append(admission, request_id=request_id, authority=authority, payload=payload)
        raise RuntimeError("forced required audit failure")


@pytest.mark.asyncio
@pytest.mark.parametrize("audit_failure", [False, True])
async def test_rejected_admission_leaves_no_job_audit_or_reservation(
    database: Database, audit_failure: bool
) -> None:
    request, authority = await _request(database)
    expected = RuntimeError if audit_failure else UnsupportedJobPayloadError
    with pytest.raises(
        expected, match="forced required audit failure" if audit_failure else "does not support"
    ):
        async with database.session() as session, session.begin():
            service = JobAdmissionService(
                ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
                AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
                IdempotencyService(PostgresOperationReservationWriter(session)),
                PostgresJobStore(session),
                MockFailingJobAdmissionAuditWriter(session)
                if audit_failure
                else PostgresJobAdmissionAuditWriter(session),
                supported_payloads=(("test.progress", 1),),
            )
            await service.admit(
                access=AccessContextDTO(
                    authority.principal_id, MockAuthenticationEvidence.application_key()
                ),
                authority=authority,
                context=OperationAdmissionContextDTO(
                    request.method, request.requested_route, request.key
                ),
                fingerprint=RequestFingerprint(request.fingerprint),
                request_id=RequestId(uuid4()),
                payload=JobPayload("test.progress", 1 if audit_failure else 2, b"fixed"),
            )
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 0


async def _wait_job(
    database: Database, admission: JobAdmissionDTO, *, checkpoint: bytes | None = None
) -> None:
    async with asyncio.timeout(20):
        while True:
            async with database.session() as session:
                saved = await PostgresJobStore(session).find(admission.operation_id)
            if saved is not None and (
                saved.status is JobStatus.SUCCEEDED
                if checkpoint is None
                else saved.checkpoint >= checkpoint
            ):
                return
            await asyncio.sleep(0.02)


@pytest.mark.asyncio
async def test_real_bounded_handler_completes_through_worker_checkpoints(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    admission = await _admit(database, data=b"3")
    async with application_worker_process(temporary_postgres_settings) as (_, units):
        await _wait_job(database, admission)
    assert units == [1, 2, 3]


@pytest.mark.asyncio
async def test_worker_process_replacement_keeps_original_job_and_skips_completed_units(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    admission = await _admit(database, data=b"restart")
    async with application_worker_process(temporary_postgres_settings, allow_killed=True) as (
        process,
        _,
    ):
        await _wait_job(database, admission, checkpoint=b"1")
        process.kill()
        await process.wait()
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == admission.job_id.value)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    async with application_worker_process(temporary_postgres_settings) as (_, second_units):
        await _wait_job(database, admission)
    assert second_units == [2, 3]
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admission.operation_id)
    assert saved is not None and saved.job_id == admission.job_id and saved.attempt == 2


async def _human_request(
    database: Database,
) -> tuple[OperationReservationRequestDTO, AdmittedWorkAuthorityDTO, AccessContextDTO]:
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
    )
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True
        )
        await session.execute(
            update(ProjectActionGrantRow)
            .where(ProjectActionGrantRow.project_id == scenario.project_id.value)
            .values(action="create-sources")
        )
        installation = await session.scalar(select(InstallationIdentityRow.installation_id))
        assert installation is not None
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=scenario.organization_id.value,
                principal_id=scenario.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        session.add(
            HumanCredentialVersionRow(
                installation_id=installation,
                authority=identity.authority.value,
                subject=identity.subject.value,
                version=1,
            )
        )
    binding = HumanOAuthCredentialBindingDTO(
        identity, InstallationId(installation), HumanCredentialVersion(1)
    )
    authority = AdmittedWorkAuthorityDTO(
        scenario.principal_id,
        PrincipalKind.HUMAN,
        InstallationId(installation),
        scenario.organization_id,
        scenario.project_id,
        ActionId("create-sources"),
        binding,
    )
    request = OperationReservationRequestDTO(
        principal_id=scenario.principal_id,
        organization_id=scenario.organization_id,
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/sources",
        key=IdempotencyKey("human-job"),
        fingerprint=b"H" * 32,
    )
    return request, authority, AccessContextDTO(scenario.principal_id, binding)


def _admission_service(session: AsyncSession) -> JobAdmissionService:
    return JobAdmissionService(
        ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
        AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
        IdempotencyService(PostgresOperationReservationWriter(session)),
        PostgresJobStore(session),
        PostgresJobAdmissionAuditWriter(session),
        supported_payloads=(("test.progress", 1),),
    )


async def _human_admit(
    database: Database,
    request: OperationReservationRequestDTO,
    authority: AdmittedWorkAuthorityDTO,
    access: AccessContextDTO,
) -> JobAdmissionDTO:
    async with database.session() as session, session.begin():
        return await _admission_service(session).admit(
            access=access,
            authority=authority,
            context=OperationAdmissionContextDTO(
                request.method, request.requested_route, request.key
            ),
            fingerprint=RequestFingerprint(request.fingerprint),
            request_id=RequestId(uuid4()),
            payload=JobPayload("test.progress", 1, b"3"),
        )


@pytest.mark.asyncio
async def test_browser_admission_is_rejected_before_any_durable_effect(database: Database) -> None:
    request, authority, access = await _human_request(database)
    assert authority.human_binding is not None
    browser = replace(
        access,
        authentication_evidence=MockAuthenticationEvidence.browser(
            authority.human_binding.identity
        ),
    )
    with pytest.raises(InvalidInputError, match="Browser"):
        await _human_admit(database, request, authority, browser)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 0
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 0


@pytest.mark.asyncio
async def test_old_human_generation_stops_after_recovery_block_is_gone(database: Database) -> None:
    request, authority, access = await _human_request(database)
    admission = await _human_admit(database, request, authority, access)
    context = await _claim(database)
    assert context is not None
    async with database.session() as session, session.begin():
        await session.execute(update(HumanCredentialVersionRow).values(version=2))
        facts = await PostgresAdmittedWorkFactsReader(session).read(authority)
        assert facts is not None and not facts.has_pending_recovery
    with pytest.raises(JobStoppedError):
        await _checkpoints(database, context, b"old-generation-result")
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admission.operation_id)
    assert (
        saved is not None
        and saved.status is JobStatus.FAILED
        and saved.reason == "authority_changed"
        and saved.checkpoint == b""
    )


@pytest.mark.asyncio
async def test_fresh_oauth_replay_preserves_original_admitted_generation(
    database: Database,
) -> None:
    request, authority, access = await _human_request(database)
    first = await _human_admit(database, request, authority, access)
    assert authority.human_binding is not None
    fresh_binding = replace(authority.human_binding, version=HumanCredentialVersion(2))
    async with database.session() as session, session.begin():
        await session.execute(update(HumanCredentialVersionRow).values(version=2))
    replay = await _human_admit(
        database,
        request,
        replace(authority, human_binding=fresh_binding),
        replace(access, authentication_evidence=fresh_binding),
    )
    assert (
        replay.job_id == first.job_id
        and replay.operation_id == first.operation_id
        and not replay.created
    )
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(first.operation_id)
    assert saved is not None and saved.authority == authority and saved.status is JobStatus.QUEUED


@pytest.mark.asyncio
async def test_worker_refuses_incompatible_schema_without_migrating(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with database.session() as session, session.begin():
        await session.execute(
            update(AlembicVersionRow).values(version_num="0009_operation_lookup_authority")
        )
    code, output = await application_worker_command(temporary_postgres_settings)
    assert (
        code == 1
        and "application_worker_ready" not in output
        and temporary_postgres_settings.password.get_secret_value() not in output
    )
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0009_operation_lookup_authority"
        )


@pytest.mark.asyncio
async def test_worker_missing_installation_identity_never_reports_ready(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    async with database.session() as session, session.begin():
        await session.execute(delete(InstallationIdentityRow))
    code, output = await application_worker_command(temporary_postgres_settings)
    assert code == 1 and "application_worker_ready" not in output
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(InstallationIdentityRow)) == 0


@pytest.mark.asyncio
async def test_long_unit_renews_lease_while_another_worker_polls(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    admission = await _admit(database, data=b"slow")
    async with application_worker_process(temporary_postgres_settings) as (_, first_units):
        async with asyncio.timeout(5):
            while True:
                async with database.session() as session:
                    saved = await PostgresJobStore(session).find(admission.operation_id)
                if saved is not None and saved.status is JobStatus.RUNNING:
                    break
                await asyncio.sleep(0.02)
        async with application_worker_process(temporary_postgres_settings) as (_, second_units):
            await _wait_job(database, admission)
    assert first_units == [1] and second_units == []
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admission.operation_id)
    assert saved is not None and saved.attempt == 1


@pytest.mark.asyncio
async def test_bounded_shutdown_preserves_progress_without_canceling_job(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    admission = await _admit(database, data=b"blocked")
    async with application_worker_process(temporary_postgres_settings):
        await _wait_job(database, admission, checkpoint=b"1")
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admission.operation_id)
    assert (
        saved is not None
        and saved.status is JobStatus.RUNNING
        and saved.checkpoint == b"1"
        and not saved.cancel_requested
    )


@pytest.mark.asyncio
async def test_full_eight_job_queue_still_accepts_cancellation(database: Database) -> None:
    admissions = [await _admit(database) for _ in range(8)]
    with pytest.raises(JobQueueFullError):
        await _admit(database)
    async with database.session() as session, session.begin():
        await PostgresJobStore(session).request_cancel(admissions[0].job_id)
    assert await _claim(database) is None
    context = await _claim(database)
    assert context is not None and context.job_id == admissions[1].job_id
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 8
        first = await PostgresJobStore(session).find(admissions[0].operation_id)
    assert first is not None and first.status is JobStatus.CANCELED


@pytest.mark.asyncio
async def test_terminal_success_cannot_be_requeued_by_attempt_retirement(
    database: Database,
) -> None:
    admission = await _admit(database)
    context = await _claim(database)
    assert context is not None
    async with database.session() as session, session.begin():
        await PostgresJobStore(session).finish(context, status=JobStatus.SUCCEEDED, reason=None)
    async with database.session() as session:
        terminal = await PostgresJobStore(session).find(admission.operation_id)
    assert terminal is not None
    with pytest.raises(JobFenceLostError):
        async with database.session() as session, session.begin():
            await PostgresJobStore(session).retire_attempt(
                terminal,
                status=JobStatus.QUEUED,
                reason="stale_decision",
                due_at=terminal.observed_at,
            )
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admission.operation_id)
    assert saved is not None and saved.status is JobStatus.SUCCEEDED and saved.attempt == 1


@pytest.mark.asyncio
async def test_queued_snapshot_cannot_retire_a_later_retry(database: Database) -> None:
    admission = await _admit(database)
    async with database.session() as session:
        original = await PostgresJobStore(session).find(admission.operation_id)
    assert original is not None
    context = await _claim(database)
    assert context is not None
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == admission.job_id.value)
            .values(lease_expires_at=func.clock_timestamp() - timedelta(seconds=1))
        )
    assert await _claim(database) is None
    with pytest.raises(JobFenceLostError):
        async with database.session() as session, session.begin():
            await PostgresJobStore(session).retire_attempt(
                original,
                status=JobStatus.FAILED,
                reason="stale_decision",
                due_at=original.observed_at,
            )
    async with database.session() as session:
        saved = await PostgresJobStore(session).find(admission.operation_id)
    assert saved is not None and saved.status is JobStatus.QUEUED and saved.attempt == 1
