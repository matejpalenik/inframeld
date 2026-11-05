"""Seed real scoped ownership without creating a product principal or reservation."""

from dataclasses import dataclass
from typing import override
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_artifact_cleanup_audit_writer import (
    PostgresArtifactCleanupAuditWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_capacity_dto import ArtifactCapacityDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.protocols.artifact_capacity_reader import (
    ArtifactCapacityReader,
)
from inframeld_backend.shared.application.services.artifact_allocation_service import (
    ArtifactAllocationService,
)
from inframeld_backend.shared.application.services.artifact_cleanup_admission_service import (
    ArtifactCleanupAdmissionService,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.services.job_checkpoint_service import (
    JobCheckpointService,
)
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_attempt_repository import (
    PostgresArtifactAttemptRepository,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_cleanup_obligation_repository import (
    PostgresArtifactCleanupObligationRepository,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_artifact_cleanup_admission_writer import (
    PostgresArtifactCleanupAdmissionWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.authentication_evidence import MockAuthenticationEvidence


@dataclass(frozen=True, slots=True)
class ArtifactScenario:
    scope: ArtifactScopeDTO
    artifact_id: ArtifactId
    attempt_id: ArtifactAttemptId
    reservation_id: ArtifactStagingReservationId
    obligation_id: ArtifactCleanupObligationId
    origin: BusinessOperationArtifactOriginDTO | UnadmittedStagingArtifactOriginDTO


class MockArtifactCapacityReader(ArtifactCapacityReader):
    def __init__(self, observation: ArtifactCapacityDTO | None = None) -> None:
        self._observation = observation or ArtifactCapacityDTO(1024**4, 900 * 1024**3)

    @override
    async def read(self) -> ArtifactCapacityDTO:
        return self._observation


async def seed_artifact_scope(database: Database) -> ArtifactScopeDTO:
    async with database.session() as session, session.begin():
        installation = await session.scalar(select(InstallationIdentityRow.installation_id))
        assert installation is not None
        organization, project = uuid4(), uuid4()
        session.add(OrganizationRow(id=organization, name="Support"))
        await session.flush()
        session.add(
            ProjectRow(
                id=project,
                organization_id=organization,
                name="Support",
                status=ProjectStatus.ACTIVE,
            )
        )
    return ArtifactScopeDTO(
        InstallationId(installation), OrganizationId(organization), ProjectId(project)
    )


def artifact_scenario(
    scope: ArtifactScopeDTO, origin: BusinessOperationArtifactOriginDTO | None = None
) -> ArtifactScenario:
    attempt = ArtifactAttemptId(uuid4())
    return ArtifactScenario(
        scope,
        ArtifactId(uuid4()),
        attempt,
        ArtifactStagingReservationId(uuid4()),
        ArtifactCleanupObligationId(uuid4()),
        origin
        if origin is not None
        else UnadmittedStagingArtifactOriginDTO(attempt, RequestId(uuid4())),
    )


def artifact_allocator(
    session: AsyncSession,
    *,
    capacity: int = 8,
    physical_capacity: ArtifactCapacityDTO | None = None,
) -> ArtifactAllocationService:
    return ArtifactAllocationService(
        SqlAlchemyTransactionManager(session),
        PostgresArtifactAttemptRepository(session),
        PostgresArtifactCleanupObligationRepository(session),
        ArtifactCleanupAdmissionService(
            PostgresArtifactCleanupAdmissionWriter(session),
            PostgresArtifactCleanupAuditWriter(session),
            capacity=capacity,
        ),
        MockArtifactCapacityReader(physical_capacity),
    )


async def allocate_artifact(
    database: Database,
    scenario: ArtifactScenario,
    *,
    capacity: int = 8,
    transfer_seconds: float = 7200,
    limit_bytes: int = 25 * 1024 * 1024,
    physical_capacity: ArtifactCapacityDTO | None = None,
) -> ArtifactAllocationDTO:
    async with database.session() as session:
        return await artifact_allocator(
            session, capacity=capacity, physical_capacity=physical_capacity
        ).allocate(
            scope=scenario.scope,
            artifact_id=scenario.artifact_id,
            attempt_id=scenario.attempt_id,
            reservation_id=scenario.reservation_id,
            obligation_id=scenario.obligation_id,
            origin=scenario.origin,
            transfer_seconds=transfer_seconds,
            limit_bytes=limit_bytes,
        )


async def completed_product_origin(
    database: Database,
    scope: ArtifactScopeDTO | None = None,
) -> tuple[ArtifactScopeDTO, BusinessOperationArtifactOriginDTO]:
    """Complete a genuine ordinary job through admission, current authority and replay.

    Cleanup later retains this business attribution. It receives no fabricated
    product reservation or application principal of its own.
    """

    if scope is None:
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
        scope = ArtifactScopeDTO(
            InstallationId(installation), seed.organization_id, seed.project_id
        )
        actor = seed.principal_id
    else:
        async with database.session() as session:
            principal = await session.scalar(
                select(ProjectActionGrantRow.recipient_principal_id).where(
                    ProjectActionGrantRow.project_id == scope.project_id.value,
                    ProjectActionGrantRow.action == "inspect-feedback",
                )
            )
            assert principal is not None
            actor = PrincipalId(principal)
    authority = AdmittedWorkAuthorityDTO(
        actor,
        PrincipalKind.APPLICATION,
        scope.installation_id,
        scope.organization_id,
        scope.project_id,
        ActionId("inspect-feedback"),
        None,
    )
    request_id = RequestId(uuid4())
    async with database.session() as session, session.begin():
        admission = await JobAdmissionService(
            ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            IdempotencyService(PostgresOperationReservationWriter(session)),
            PostgresJobStore(session),
            PostgresJobAdmissionAuditWriter(session),
            supported_payloads=(("test.progress", 1),),
        ).admit(
            access=AccessContextDTO(actor, MockAuthenticationEvidence.application_key()),
            authority=authority,
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                "/test/projects/{project_id}/feedback-reports",
                IdempotencyKey("artifact-work-" + uuid4().hex),
            ),
            fingerprint=RequestFingerprint(b"F" * 32),
            request_id=request_id,
            payload=JobPayload("test.progress", 1, b"1"),
        )
    async with database.session() as session:
        context = await JobExecutionService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            supported_payloads=(("test.progress", 1),),
            worker_id=uuid4(),
        ).claim_next()
        assert context is not None and context.job_id == admission.job_id
        await JobCheckpointService(
            SqlAlchemyTransactionManager(session),
            PostgresJobStore(session),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
        ).succeed(context)
    return scope, BusinessOperationArtifactOriginDTO(admission.operation_id, request_id)
