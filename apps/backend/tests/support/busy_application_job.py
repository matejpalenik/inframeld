"""Hold one real ordinary attempt while the dedicated recovery command completes."""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from uuid import uuid4

from sqlalchemy import select, update

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
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
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
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.authentication_evidence import MockAuthenticationEvidence


@asynccontextmanager
async def busy_application_job(database: Database) -> AsyncGenerator[JobAttemptContextDTO]:
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_kind=PrincipalKind.APPLICATION,
        )
        await session.execute(
            update(ProjectActionGrantRow)
            .where(ProjectActionGrantRow.project_id == seed.project_id.value)
            .values(action="inspect-feedback")
        )
        installation = await session.scalar(select(InstallationIdentityRow.installation_id))
        assert installation is not None
        authority = AdmittedWorkAuthorityDTO(
            seed.principal_id,
            PrincipalKind.APPLICATION,
            InstallationId(installation),
            seed.organization_id,
            seed.project_id,
            ActionId("inspect-feedback"),
            None,
        )
        service = JobAdmissionService(
            ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            IdempotencyService(PostgresOperationReservationWriter(session)),
            PostgresJobStore(session),
            PostgresJobAdmissionAuditWriter(session),
            supported_payloads=(("test.busy", 1),),
        )
        admission = await service.admit(
            access=AccessContextDTO(
                seed.principal_id, MockAuthenticationEvidence.application_key()
            ),
            authority=authority,
            context=OperationAdmissionContextDTO(
                "POST", "/test/projects/{project_id}/feedback-reports", IdempotencyKey(str(uuid4()))
            ),
            fingerprint=RequestFingerprint(b"B" * 32),
            request_id=RequestId(uuid4()),
            payload=JobPayload("test.busy", 1, b"bounded-busy-ordinary-slot"),
        )
    async with database.session() as session:
        context = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("test.busy", 1),),
            worker_id=uuid4(),
            lease_seconds=120,
            work_seconds=600,
        ).claim_next()
    assert context is not None and context.job_id == admission.job_id

    async def finish() -> None:
        async with asyncio.timeout(5), database.session() as session, session.begin():
            await PostgresJobStore(session).finish(context, status=JobStatus.SUCCEEDED, reason=None)

    try:
        yield context
    finally:
        task = asyncio.create_task(finish())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.gather(task, return_exceptions=True)
            raise
