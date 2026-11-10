"""Check retained deletion integrity with controlled observations, not a database admission proof."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.project_deletion_job_facts_dto import (
    ProjectDeletionJobFactsDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.project_deletion_job_facts_reader import (
    ProjectDeletionJobFactsReader,
)
from inframeld_backend.shared.application.services.project_deletion_job_authorization_service import (
    ProjectDeletionJobAuthorizationService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

RECORDED = datetime(2026, 1, 1, tzinfo=UTC)
ADMITTED = RECORDED + timedelta(seconds=1)
OBSERVED = ADMITTED + timedelta(seconds=30)
JOB = JobId(UUID(int=10))
BINDING = ProjectDeletionJobBindingDTO(
    obligation_id=UUID(int=11),
    operation_id=OperationId("original-project-deletion"),
    request_id=RequestId(UUID(int=12)),
    installation_id=InstallationId(UUID(int=13)),
    organization_id=UUID(int=14),
    project_id=UUID(int=15),
    initiator_principal_id=UUID(int=16),
    key=IdempotencyKey("original-key"),
    fingerprint=RequestFingerprint(b"F" * 32),
    before_access_revision=7,
    access_revision=8,
)
ORIGINAL = DeletionStatusBindingDTO(
    operation_id=BINDING.operation_id,
    request_id=BINDING.request_id,
    installation_id=BINDING.installation_id,
    organization_id=OrganizationId(BINDING.organization_id),
    project_id=ProjectId(BINDING.project_id),
    initiator_principal_id=PrincipalId(BINDING.initiator_principal_id),
    method=HttpMethod.DELETE,
    requested_route="/v1/projects/00000000-0000-0000-0000-00000000000f",
    key=BINDING.key,
    fingerprint=BINDING.fingerprint,
    authority_family=OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
    action_id=ActionId("delete-project"),
    recorded_at=RECORDED,
    retention_days=30,
    retention_policy_version="ADR-0117/PD-KNOWLEDGE-02:v1",
)
FACTS = ProjectDeletionJobFactsDTO(
    binding=BINDING,
    job_id=JOB,
    payload=JobPayload("project.application-shutdown", 1, b"\0" * 15 + b"\x0b"),
    original=ORIGINAL,
    admitted_at=ADMITTED,
    observed_at=OBSERVED,
    source_revision=1,
)


class MockFacts(ProjectDeletionJobFactsReader):
    def __init__(self) -> None:
        self.result: ProjectDeletionJobFactsDTO | None = FACTS
        self.error: BaseException | None = None
        self.calls: list[UUID] = []

    @override
    async def read(self, obligation_id: UUID) -> ProjectDeletionJobFactsDTO | None:
        self.calls.append(obligation_id)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_exact_persisted_binding_and_child_are_required_once_without_native_history() -> None:
    reader = MockFacts()
    result = await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)
    assert result is FACTS
    assert reader.calls == [BINDING.obligation_id]
    assert result.original.authority_family is OperationLookupAuthorityFamily.PROJECT_ACTION_USE


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        None,
        replace(FACTS, job_id=JobId(UUID(int=99))),
        replace(FACTS, binding=replace(BINDING, obligation_id=UUID(int=99))),
        replace(FACTS, binding=replace(BINDING, operation_id=OperationId("other"))),
        replace(FACTS, binding=replace(BINDING, request_id=RequestId(UUID(int=99)))),
        replace(FACTS, binding=replace(BINDING, installation_id=InstallationId(UUID(int=99)))),
        replace(FACTS, binding=replace(BINDING, organization_id=UUID(int=99))),
        replace(FACTS, binding=replace(BINDING, project_id=UUID(int=99))),
        replace(FACTS, binding=replace(BINDING, initiator_principal_id=UUID(int=99))),
        replace(FACTS, binding=replace(BINDING, key=IdempotencyKey("other"))),
        replace(FACTS, binding=replace(BINDING, fingerprint=RequestFingerprint(b"X" * 32))),
        replace(FACTS, binding=replace(BINDING, before_access_revision=8, access_revision=9)),
    ],
)
async def test_missing_or_swapped_backing_never_confirms_the_requested_obligation(
    facts: ProjectDeletionJobFactsDTO | None,
) -> None:
    reader = MockFacts()
    reader.result = facts
    with pytest.raises(AccessDeniedError):
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)
    assert reader.calls == [BINDING.obligation_id]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "original",
    [
        replace(ORIGINAL, operation_id=OperationId("other")),
        replace(ORIGINAL, request_id=RequestId(UUID(int=99))),
        replace(ORIGINAL, installation_id=InstallationId(UUID(int=99))),
        replace(ORIGINAL, organization_id=OrganizationId(UUID(int=99))),
        replace(ORIGINAL, project_id=ProjectId(UUID(int=99))),
        replace(ORIGINAL, initiator_principal_id=PrincipalId(UUID(int=99))),
        replace(ORIGINAL, key=IdempotencyKey("other")),
        replace(ORIGINAL, fingerprint=RequestFingerprint(b"X" * 32)),
        replace(ORIGINAL, method=HttpMethod.POST),
        replace(ORIGINAL, requested_route="/v1/projects/other"),
        replace(ORIGINAL, authority_family=OperationLookupAuthorityFamily.PROJECT_GRANT_READ),
        replace(ORIGINAL, authority_family=None),
        replace(ORIGINAL, action_id=ActionId("inspect-budget")),
        replace(ORIGINAL, action_id=None),
    ],
)
async def test_retained_original_must_match_native_delete_meaning(
    original: DeletionStatusBindingDTO,
) -> None:
    reader = MockFacts()
    reader.result = replace(FACTS, original=original)
    with pytest.raises(AccessDeniedError):
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        JobPayload("artifact.cleanup", 1, FACTS.payload.data),
        JobPayload("project.application-shutdown", 2, FACTS.payload.data),
        JobPayload("project.application-shutdown", 1, b"other"),
    ],
)
async def test_wrong_handler_version_or_original_payload_is_rejected(payload: JobPayload) -> None:
    reader = MockFacts()
    reader.result = replace(FACTS, payload=payload)
    with pytest.raises(AccessDeniedError):
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "binding",
    [
        replace(BINDING, before_access_revision=-1),
        replace(BINDING, before_access_revision=True),
        replace(BINDING, access_revision=7),
        replace(BINDING, access_revision=RevisionValidation.MAX_VALUE + 1),
    ],
)
async def test_matching_rows_cannot_make_invalid_admission_revisions_coherent(
    binding: ProjectDeletionJobBindingDTO,
) -> None:
    reader = MockFacts()
    reader.result = replace(FACTS, binding=binding)
    with pytest.raises(AccessDeniedError):
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, binding)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(FACTS, source_revision=0),
        replace(FACTS, source_revision=True),
        replace(FACTS, admitted_at=RECORDED - timedelta(seconds=1)),
        replace(FACTS, observed_at=ADMITTED - timedelta(seconds=1)),
        replace(FACTS, observed_at=datetime(2026, 1, 1)),
        replace(FACTS, shutdown_completed_at=OBSERVED + timedelta(seconds=1)),
        replace(FACTS, physical_cleanup_completed_at=OBSERVED),
        replace(
            FACTS,
            shutdown_completed_at=ADMITTED + timedelta(seconds=5),
            physical_cleanup_completed_at=ADMITTED + timedelta(seconds=4),
        ),
    ],
)
async def test_incoherent_progress_or_clock_observations_do_not_authorize_a_step(
    facts: ProjectDeletionJobFactsDTO,
) -> None:
    reader = MockFacts()
    reader.result = facts
    with pytest.raises(AccessDeniedError):
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)


@pytest.mark.asyncio
async def test_old_unfinished_original_has_no_invented_native_history_or_age_expiry() -> None:
    reader = MockFacts()
    reader.result = replace(FACTS, observed_at=OBSERVED + timedelta(days=400))
    assert (
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)
        == reader.result
    )


@pytest.mark.asyncio
async def test_local_completion_and_physical_completion_remain_distinct_observations() -> None:
    reader = MockFacts()
    local = replace(FACTS, shutdown_completed_at=ADMITTED + timedelta(seconds=5), source_revision=2)
    reader.result = local
    observed = await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)
    assert observed.shutdown_completed_at is not None
    assert observed.physical_cleanup_completed_at is None

    settled = replace(local, physical_cleanup_completed_at=OBSERVED, source_revision=3)
    reader.result = settled
    assert (
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)
        == settled
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [DependencyUnavailableError(), asyncio.CancelledError()])
async def test_dependency_failure_and_cancellation_propagate_without_replacement_reads(
    error: BaseException,
) -> None:
    reader = MockFacts()
    reader.error = error
    with pytest.raises(type(error)) as caught:
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)
    assert caught.value is error
    assert reader.calls == [BINDING.obligation_id]


@pytest.mark.asyncio
async def test_rejection_does_not_echo_hostile_retained_text() -> None:
    reader = MockFacts()
    reader.result = replace(
        FACTS, original=replace(ORIGINAL, requested_route="HOSTILE-secret\n/path")
    )
    with pytest.raises(AccessDeniedError) as caught:
        await ProjectDeletionJobAuthorizationService(reader).require_current(JOB, BINDING)
    assert "HOSTILE" not in str(caught.value) and "secret" not in str(caught.value)
