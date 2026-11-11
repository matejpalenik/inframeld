"""Qualify exact retained binding and pre-search current authority in PostgreSQL.

Synthetic canonical routes exercise shared admission support. They do not deliver
an upload, build or Organization business endpoint.
"""

import os
from dataclasses import replace
from datetime import timedelta
from enum import StrEnum
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select, update
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.artifact_scenarios import allocate_artifact, artifact_scenario
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.operation_lookup_authorization_service import (
    OperationLookupAuthorizationService,
)
from inframeld_backend.access.application.services.project_operation_admission_service import (
    ProjectOperationAdmissionService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_operation_lookup_facts_reader import (
    PostgresOperationLookupFactsReader,
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
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_job_admission_audit_writer import (
    PostgresJobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.dtos.accepted_operation_lookup_dto import (
    AcceptedOperationLookupDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.job_admission_service import JobAdmissionService
from inframeld_backend.shared.application.services.original_operation_lookup_service import (
    OriginalOperationLookupService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.mappers.original_operation_lookup_mapper import (
    OriginalOperationLookupMapper,
)
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.readers.postgres_operation_lookup_reader import (
    PostgresOperationLookupReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


class ChangedCase(StrEnum):
    INSTALLATION = "installation"
    PRINCIPAL = "principal"
    ORGANIZATION = "organization"
    PROJECT = "project"
    METHOD = "method"
    ROUTE = "route"
    KEY = "key"


pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)
ACTION = ActionId("create-access-groups")


async def admitted_job(
    database: Database,
) -> tuple[AccessContextDTO, LookupOriginalOperationQuery, JobAdmissionDTO]:
    """Commit a real ordinary job using controlled verified OAuth evidence.

    This exercises local admission and persisted identity, not provider token
    verification or a new product endpoint. No handler runs during inspection.
    """
    installed = await PostgresInstallationIdentityReader(database).read()
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject("job-owner-" + uuid4().hex)
    )
    binding = replace(MockAuthenticationEvidence.human_oauth(identity), installation_id=installed)
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=False
        )
        session.add_all(
            [
                ProjectActionGrantRow(
                    project_id=seed.project_id.value,
                    recipient_principal_id=seed.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=ACTION.value,
                    can_grant=False,
                ),
                HumanIdentityLinkRow(
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    organization_id=seed.organization_id.value,
                    principal_id=seed.principal_id.value,
                    principal_kind=PrincipalKind.HUMAN,
                ),
                HumanCredentialVersionRow(
                    installation_id=installed.value,
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    version=binding.version.value,
                ),
            ]
        )
    access = AccessContextDTO(seed.principal_id, binding)
    query = LookupOriginalOperationQuery(
        installed,
        seed.organization_id,
        seed.project_id,
        HttpMethod.POST,
        "/v1/original-project-operation",
        IdempotencyKey("job-reference-" + uuid4().hex),
        OperationLookupAuthority(OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ACTION),
    )
    async with database.session() as session, session.begin():
        admission = await JobAdmissionService(
            ActionAuthorizationService(PostgresProjectActionFactsReader(session)),
            AdmittedWorkAuthorizationService(PostgresAdmittedWorkFactsReader(session)),
            IdempotencyService(PostgresOperationReservationWriter(session)),
            PostgresJobStore(session),
            PostgresJobAdmissionAuditWriter(session),
            supported_payloads=(("test.lookup-reference", 1),),
        ).admit(
            access=access,
            authority=AdmittedWorkAuthorityDTO(
                principal_id=seed.principal_id,
                principal_kind=PrincipalKind.HUMAN,
                installation_id=installed,
                organization_id=seed.organization_id,
                project_id=seed.project_id,
                action_id=ACTION,
                human_binding=binding,
            ),
            context=IdempotencyContextDTO(query.method, query.requested_route, query.key),
            fingerprint=RequestFingerprint(b"R" * 32),
            request_id=RequestId(uuid4()),
            payload=JobPayload("test.lookup-reference", 1, b"private-worker-input"),
        )
    return access, query, admission


@pytest.mark.asyncio
async def test_real_ordinary_admission_lookup_returns_original_job_reference_without_writes(
    database: Database,
) -> None:
    access, query, admission = await admitted_job(database)
    async with database.session() as session:
        job_state = select(
            DurableJobRow.id,
            DurableJobRow.operation_id,
            DurableJobRow.request_id,
            DurableJobRow.status,
            DurableJobRow.attempt_count,
            DurableJobRow.fence,
            DurableJobRow.lease_expires_at,
            DurableJobRow.checkpoint,
            DurableJobRow.pending_effect,
            DurableJobRow.payload,
            DurableJobRow.human_version,
            DurableJobRow.queued_deadline,
            DurableJobRow.work_deadline,
            DurableJobRow.cancel_requested,
        )
        operation_state = select(
            IdempotencyReservationRow.operation_id,
            IdempotencyReservationRow.state,
            IdempotencyReservationRow.replay_kind,
            IdempotencyReservationRow.created_at,
            IdempotencyReservationRow.expires_at,
        )
        before_job = (await session.execute(job_state)).tuples().all()
        before_operation = (await session.execute(operation_state)).tuples().all()
        result = await OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        ).lookup(access=access, query=query)

        assert result == AcceptedOperationLookupDTO(admission.operation_id, None, admission.job_id)
        assert OriginalOperationLookupMapper.to_response(result).model_dump(
            by_alias=True, mode="json"
        ) == {
            "outcome": "accepted_asynchronous",
            "operationId": admission.operation_id.value,
            "admission": "confirmed",
            "jobReference": {"jobId": str(admission.job_id.value)},
            "dispatch": "not_established",
            "idempotencyExpiresAt": None,
        }
        assert (await session.execute(job_state)).tuples().all() == before_job
        assert (await session.execute(operation_state)).tuples().all() == before_operation
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1
        assert await session.scalar(select(func.count()).select_from(ApplicationJobQueueRow)) == 1
        assert await session.scalar(select(func.count()).select_from(DurableJobAttemptRow)) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", list(JobStatus))
async def test_known_reference_does_not_claim_current_job_state(
    database: Database, status: JobStatus
) -> None:
    """Controlled persisted states affect neither admission identity nor dispatch facts."""
    access, query, admission = await admitted_job(database)
    async with database.session() as session, session.begin():
        await session.execute(
            update(DurableJobRow)
            .where(DurableJobRow.id == admission.job_id.value)
            .values(status=status.value, checkpoint=b"private-progress", pending_effect="external")
        )
    async with database.session() as session:
        result = await OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        ).lookup(access=access, query=query)
    assert result == AcceptedOperationLookupDTO(admission.operation_id, None, admission.job_id)
    assert (
        OriginalOperationLookupMapper.to_response(result).model_dump(by_alias=True)["dispatch"]
        == "not_established"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        ChangedCase.INSTALLATION,
        "actor",
        "kind",
        ChangedCase.ORGANIZATION,
        ChangedCase.PROJECT,
        "action",
        "missing_authority",
        "bad_authority",
        "missing_subject",
        "bad_subject",
        "missing_generation",
        "bad_generation",
        "missing_identity_link",
    ],
)
async def test_optional_job_binding_failure_preserves_confirmed_admission(
    database: Database, changed: str
) -> None:
    """Simulate damaged or non-authoritative optional metadata without repairing it."""
    access, query, admission = await admitted_job(database)
    async with database.session() as session, session.begin():
        job = await session.get(DurableJobRow, admission.job_id.value)
        assert job is not None
        match changed:
            case ChangedCase.INSTALLATION:
                job.installation_id = uuid4()
            case "actor":
                job.principal_id = uuid4()
            case "kind":
                job.principal_kind = PrincipalKind.APPLICATION.value
            case ChangedCase.ORGANIZATION:
                job.organization_id = uuid4()
            case ChangedCase.PROJECT:
                job.project_id = uuid4()
            case "action":
                job.action_id = "inspect-budget"
            case "missing_authority":
                job.human_authority = None
            case "bad_authority":
                job.human_authority = ""
            case "missing_subject":
                job.human_subject = None
            case "bad_subject":
                job.human_subject = ""
            case "missing_generation":
                job.human_version = None
            case "bad_generation":
                job.human_version = 0
            case "missing_identity_link":
                job.human_subject = "unlinked-original-human"
            case _:
                raise AssertionError(changed)
    async with database.session() as session:
        result = await OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        ).lookup(access=access, query=query)
        assert result == AcceptedOperationLookupDTO(admission.operation_id, None)
        job = await session.get(DurableJobRow, admission.job_id.value)
        assert job is not None and job.attempt_count == 0 and job.checkpoint == b""
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1


@pytest.mark.asyncio
async def test_fresh_current_generation_can_observe_original_generation_job(
    database: Database,
) -> None:
    """Change the authoritative generation without synthesizing recovery completion."""
    access, query, admission = await admitted_job(database)
    async with database.session() as session, session.begin():
        await session.execute(update(HumanCredentialVersionRow).values(version=2))
    async with database.session() as session:
        service = OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        )
        with pytest.raises(HumanOAuthCredentialRejectedError):
            await service.lookup(access=access, query=query)
        assert isinstance(access.authentication_evidence, HumanOAuthCredentialBindingDTO)
        current = replace(
            access,
            authentication_evidence=replace(
                access.authentication_evidence, version=HumanCredentialVersion(2)
            ),
        )
        result = await service.lookup(access=current, query=query)
        assert result == AcceptedOperationLookupDTO(admission.operation_id, None, admission.job_id)
        job = await session.get(DurableJobRow, admission.job_id.value)
        assert job is not None and job.human_version == 1 and job.attempt_count == 0


@pytest.mark.asyncio
async def test_revoked_read_cannot_disclose_known_job(database: Database) -> None:
    access, query, _admission = await admitted_job(database)
    async with database.session() as session, session.begin():
        await session.execute(delete(ProjectActionGrantRow))
    async with database.session() as session:
        with pytest.raises(AccessDeniedError):
            await OriginalOperationLookupService(
                OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
                PostgresOperationLookupReader(session),
            ).lookup(access=access, query=query)


@pytest.mark.asyncio
async def test_another_accessible_project_cannot_retarget_original_job(database: Database) -> None:
    access, query, admission = await admitted_job(database)
    another = ProjectId(uuid4())
    async with database.session() as session, session.begin():
        session.add(
            ProjectRow(
                id=another.value,
                organization_id=query.organization_id.value,
                name="Another project",
                status=ProjectStatus.ACTIVE,
            )
        )
        await session.flush()
        session.add(
            ProjectMembershipRow(
                project_id=another.value,
                principal_id=access.actor_principal_id.value,
                organization_id=query.organization_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()
        session.add(
            ProjectActionGrantRow(
                project_id=another.value,
                recipient_principal_id=access.actor_principal_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ACTION.value,
                can_grant=False,
            )
        )
    async with database.session() as session:
        service = OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        )
        assert await service.lookup(access=access, query=replace(query, project_id=another)) == (
            UnresolvedOperationDTO()
        )
        assert await service.lookup(access=access, query=query) == AcceptedOperationLookupDTO(
            admission.operation_id, None, admission.job_id
        )


@pytest.mark.asyncio
async def test_cleanup_business_origin_never_substitutes_product_job_reference(
    database: Database,
) -> None:
    access, query, admission = await admitted_job(database)
    assert query.project_id is not None
    async with database.session() as session:
        job = await session.get(DurableJobRow, admission.job_id.value)
        assert job is not None
        original_request = RequestId(job.request_id)
    allocation = await allocate_artifact(
        database,
        artifact_scenario(
            ArtifactScopeDTO(query.installation_id, query.organization_id, query.project_id),
            BusinessOperationArtifactOriginDTO(admission.operation_id, original_request),
        ),
    )
    assert allocation.cleanup_job_id != admission.job_id
    async with database.session() as session:
        service = OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        )
        assert await service.lookup(access=access, query=query) == AcceptedOperationLookupDTO(
            admission.operation_id, None, admission.job_id
        )
    # Simulate missing optional product metadata, preserving the real cleanup
    # obligation and its original business attribution.
    async with database.session() as session, session.begin():
        await session.execute(
            delete(DurableJobRow).where(DurableJobRow.id == admission.job_id.value)
        )
    async with database.session() as session:
        result = await OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        ).lookup(access=access, query=query)
        assert result == AcceptedOperationLookupDTO(admission.operation_id, None)
        assert await session.get(DurableJobRow, allocation.cleanup_job_id.value) is not None


async def admitted(
    database: Database, kind: OperationReplayKind | None = OperationReplayKind.ASYNC_JOB
) -> tuple[AccessContextDTO, LookupOriginalOperationQuery, str]:
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
    )
    async with database.session() as session, session.begin():
        seed = await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=False
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
        session.add(
            HumanIdentityLinkRow(
                authority=identity.authority.value,
                subject=identity.subject.value,
                organization_id=seed.organization_id.value,
                principal_id=seed.principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )

    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    access = AccessContextDTO(
        seed.principal_id,
        BrowserSessionAuthenticationDTO(identity, state.installation_id, state.version),
    )
    query = LookupOriginalOperationQuery(
        state.installation_id,
        seed.organization_id,
        seed.project_id,
        HttpMethod.POST,
        "/v1/original-project-operation",
        IdempotencyKey("lost-ack"),
        OperationLookupAuthority(OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ACTION),
    )
    async with database.session() as session, session.begin():
        idempotency = IdempotencyService(PostgresOperationReservationWriter(session))
        reservation = await ProjectOperationAdmissionService(
            ActionAuthorizationService(PostgresProjectActionFactsReader(session)), idempotency
        ).reserve(
            access=access,
            action_id=ACTION,
            request=ProjectOperationAdmissionRequestDTO(
                seed.project_id,
                query.method,
                query.requested_route,
                query.key,
                RequestFingerprint(b"F" * 32),
            ),
            expected_replay_kind=kind or OperationReplayKind.SAFE_RESULT,
        )
        assert isinstance(reservation, NewOperationReservationDTO)
        if kind is not None:
            await idempotency.record_completed_result(reservation, replay_kind=kind)
    return access, query, reservation.operation_id.value


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(OperationReplayKind))
async def test_retained_outcome_can_be_read_without_reserving_again(
    database: Database, kind: OperationReplayKind
) -> None:
    access, query, operation = await admitted(database, kind)
    async with database.session() as session:
        before = (
            (
                await session.execute(
                    select(
                        IdempotencyReservationRow.operation_id,
                        IdempotencyReservationRow.created_at,
                        IdempotencyReservationRow.expires_at,
                    )
                )
            )
            .tuples()
            .all()
        )
        result = await PostgresOperationLookupReader(session).read(
            principal_id=access.actor_principal_id, query=query
        )
        assert result is not None
        assert result.operation.operation_id.value == operation
        assert result.operation.created is False
        assert result.operation.replay_kind is kind
        assert result.job_id is None
        after = (
            (
                await session.execute(
                    select(
                        IdempotencyReservationRow.operation_id,
                        IdempotencyReservationRow.created_at,
                        IdempotencyReservationRow.expires_at,
                    )
                )
            )
            .tuples()
            .all()
        )
        assert after == before


@pytest.mark.asyncio
async def test_original_action_binding_is_saved_with_admission(database: Database) -> None:
    _access, query, operation = await admitted(database)
    async with database.session() as session:
        row = await session.get(IdempotencyReservationRow, operation)
        assert row is not None
        assert row.lookup_authority_family == query.expected_authority.family.value
        assert row.lookup_action_id == ACTION.value


@pytest.mark.asyncio
async def test_async_lookup_keeps_admission_and_explicitly_has_no_known_job(
    database: Database,
) -> None:
    access, query, operation = await admitted(database)
    async with database.session() as session:
        service = OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        )
        result = await service.lookup(access=access, query=query)
    assert isinstance(result, AcceptedOperationLookupDTO)
    assert result.operation_id.value == operation
    assert result.expires_at is None
    assert result.job_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["retained", "absent", "legacy", "different_guard"])
async def test_denied_guard_is_independent_of_history(database: Database, history: str) -> None:
    access, query, operation = await admitted(database)
    assert query.project_id is not None
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectActionGrantRow)
            .where(ProjectActionGrantRow.project_id == query.project_id.value)
            .values(can_grant=False)
        )
        if history == "absent":
            query = replace(query, key=IdempotencyKey("absent"))
        elif history == "legacy":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_authority_family=None, lookup_action_id=None)
            )
        query = replace(
            query,
            requested_route="/v1/projects/{project_id}/grants",
            expected_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ACTION
            ),
        )
    async with database.session() as session:
        with pytest.raises(AccessDeniedError):
            await OriginalOperationLookupService(
                OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
                PostgresOperationLookupReader(session),
            ).lookup(access=access, query=query)


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["absent", "legacy", "different_guard", "expired"])
async def test_authorized_nonmatches_are_uniformly_unresolved(
    database: Database, history: str
) -> None:
    access, query, operation = await admitted(database, OperationReplayKind.SAFE_RESULT)
    async with database.session() as session, session.begin():
        if history == "absent":
            query = replace(query, key=IdempotencyKey("absent"))
        elif history == "legacy":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_authority_family=None, lookup_action_id=None)
            )
        elif history == "different_guard":
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(lookup_authority_family="project_grant_read")
            )
        else:
            await session.execute(
                update(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.operation_id == operation)
                .values(expires_at=func.clock_timestamp() - timedelta(seconds=1))
            )
    async with database.session() as session:
        result = await OriginalOperationLookupService(
            OperationLookupAuthorizationService(PostgresOperationLookupFactsReader(session)),
            PostgresOperationLookupReader(session),
        ).lookup(access=access, query=query)
    assert result == UnresolvedOperationDTO()


@pytest.mark.asyncio
async def test_retry_cannot_rewrite_original_authority(database: Database) -> None:
    access, query, _operation = await admitted(database)
    changed = OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("inspect-budget")
    )
    async with database.session() as session, session.begin():
        with pytest.raises(ConflictError):
            await PostgresOperationReservationWriter(session).reserve(
                OperationReservationRequestDTO(
                    principal_id=access.actor_principal_id,
                    organization_id=query.organization_id,
                    project_id=query.project_id,
                    method=query.method,
                    requested_route=query.requested_route,
                    key=query.key,
                    fingerprint=b"F" * 32,
                    lookup_authority=changed,
                )
            )


@pytest.mark.asyncio
async def test_in_progress_and_recovery_remain_distinct(database: Database) -> None:
    access, query, operation = await admitted(database, None)
    async with database.session() as session:
        result = await PostgresOperationLookupReader(session).read(
            principal_id=access.actor_principal_id, query=query
        )
        assert (
            result is not None and result.operation.state is OperationReservationState.IN_PROGRESS
        )
    async with database.session() as session, session.begin():
        await PostgresOperationReservationWriter(session).mark_recovery_required(
            result.operation.operation_id
        )
    async with database.session() as session:
        result = await PostgresOperationLookupReader(session).read(
            principal_id=access.actor_principal_id, query=query
        )
        assert (
            result is not None
            and result.operation.state is OperationReservationState.RECOVERY_REQUIRED
        )
        assert result.operation.operation_id.value == operation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        ChangedCase.INSTALLATION,
        ChangedCase.PRINCIPAL,
        ChangedCase.ORGANIZATION,
        ChangedCase.PROJECT,
        ChangedCase.METHOD,
        ChangedCase.ROUTE,
        ChangedCase.KEY,
    ],
)
async def test_retained_history_never_substitutes_another_original_identity(
    database: Database,
    changed: ChangedCase,
) -> None:
    """Every original identity component must match before any outcome is projected."""
    access, query, _operation = await admitted(database)
    principal_id = access.actor_principal_id
    match changed:
        case ChangedCase.INSTALLATION:
            query = replace(query, installation_id=InstallationId(uuid4()))
        case ChangedCase.PRINCIPAL:
            principal_id = PrincipalId(uuid4())
        case ChangedCase.ORGANIZATION:
            query = replace(query, organization_id=OrganizationId(uuid4()))
        case ChangedCase.PROJECT:
            query = replace(query, project_id=ProjectId(uuid4()))
        case ChangedCase.METHOD:
            query = replace(query, method="PATCH")
        case ChangedCase.ROUTE:
            query = replace(query, requested_route="/v1/another-original-operation")
        case ChangedCase.KEY:
            query = replace(query, key=IdempotencyKey("another-original-key"))
    async with database.session() as session:
        assert (
            await PostgresOperationLookupReader(session).read(
                principal_id=principal_id, query=query
            )
            is None
        )
