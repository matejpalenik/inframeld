"""Prove queue admission and attempt ownership against real PostgreSQL."""

import asyncio
import os
from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
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
from inframeld_backend.shared.application.enums.job_status import JobStatus
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobQueueFullError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
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
        scenario.action,
        None,
    )
    request = OperationReservationRequestDTO(
        principal_id=scenario.principal_id,
        organization_id=authority.organization_id,
        project_id=scenario.project_id,
        method="POST",
        requested_route="/v1/projects/{project_id}/builds",
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
    database: Database, *, kind: str = "test.progress", version: int = 1
) -> JobAdmissionDTO:
    request, authority = await _request(database)
    async with database.session() as session, session.begin():
        writer = PostgresOperationReservationWriter(session)
        operation = await writer.reserve(request)
        result = await PostgresJobStore(session).admit(
            operation_id=operation.operation_id,
            request_id=RequestId(uuid4()),
            authority=authority,
            payload=JobPayload(kind, version, b"fixed"),
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
