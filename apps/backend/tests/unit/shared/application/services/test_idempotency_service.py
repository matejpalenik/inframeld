from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import cast, override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
)
from inframeld_backend.shared.application.protocols.operation_reservation_writer import (
    OperationReservationWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


@dataclass(frozen=True, slots=True)
class MockAuthorizedOperationScopeDTO(AuthorizedOperationScope[ProjectId | None]):
    organization_id: OrganizationId
    project_id: ProjectId | None


EXPIRY = datetime(2030, 1, 1, tzinfo=UTC)
REQUEST = OperationReservationRequestDTO(
    principal_id=PrincipalId(UUID(int=1)),
    organization_id=OrganizationId(UUID(int=2)),
    project_id=None,
    method="POST",
    requested_route="/v1/test-operation",
    key=IdempotencyKey("retry-1"),
    fingerprint=b"F" * 32,
)
CONTEXT = OperationAdmissionContextDTO(
    method=REQUEST.method, requested_route=REQUEST.requested_route, key=REQUEST.key
)
ACCESS = AccessContextDTO(
    REQUEST.principal_id, authentication_evidence=MockAuthenticationEvidence.browser()
)
AUTHORIZATION = MockAuthorizedOperationScopeDTO(REQUEST.organization_id, REQUEST.project_id)
NEW = OperationReservationResultDTO(
    operation_id=OperationId("original-operation"),
    created=True,
    state=OperationReservationState.IN_PROGRESS,
    replay_kind=None,
    expires_at=None,
)


class MockOperationReservations(OperationReservationWriter):
    def __init__(self, result: OperationReservationResultDTO = NEW) -> None:
        self.result = result
        self.expiry: datetime | None = EXPIRY
        self.error: Exception | None = None
        self.request: OperationReservationRequestDTO | None = None
        self.completed: list[tuple[OperationId, OperationReplayKind]] = []

    @override
    async def reserve(
        self, request: OperationReservationRequestDTO
    ) -> OperationReservationResultDTO:
        self.request = request
        if self.error is not None:
            raise self.error
        return self.result

    @override
    async def mark_replayable(
        self, operation_id: OperationId, replay_kind: OperationReplayKind
    ) -> datetime | None:
        self.completed.append((operation_id, replay_kind))
        if self.error is not None:
            raise self.error
        return self.expiry


@pytest.mark.asyncio
async def test_new_reservation_keeps_its_operation_identity_and_scope() -> None:
    writer = MockOperationReservations()
    result = await IdempotencyService(writer).find_or_reserve(
        context=CONTEXT,
        access=ACCESS,
        authorization=AUTHORIZATION,
        fingerprint=RequestFingerprint(REQUEST.fingerprint),
        expected_replay_kind=OperationReplayKind.SAFE_RESULT,
    )
    assert result == NewOperationReservationDTO(NEW.operation_id)
    assert writer.request == REQUEST
    assert writer.completed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("project_id", [None, ProjectId(UUID(int=303))])
async def test_reservation_mapping_preserves_explicit_scope_and_retry_values(
    project_id: ProjectId | None,
) -> None:
    """Scope and retry values must reach storage unchanged to find the same operation."""
    writer = MockOperationReservations()
    context = OperationAdmissionContextDTO(
        method="PATCH",
        requested_route="/v1/ExampleOperations/{project_id}/",
        key=IdempotencyKey("Retry-Exact-Case"),
    )
    principal_id = PrincipalId(UUID(int=101))
    organization_id = OrganizationId(UUID(int=202))
    fingerprint = bytes(range(32))
    result = await IdempotencyService(writer).find_or_reserve(
        context=context,
        access=AccessContextDTO(
            principal_id, authentication_evidence=MockAuthenticationEvidence.browser()
        ),
        authorization=MockAuthorizedOperationScopeDTO(organization_id, project_id),
        fingerprint=RequestFingerprint(fingerprint),
        expected_replay_kind=OperationReplayKind.SAFE_RESULT,
    )
    assert result == NewOperationReservationDTO(NEW.operation_id)
    assert writer.request == OperationReservationRequestDTO(
        principal_id=principal_id,
        organization_id=organization_id,
        project_id=project_id,
        method=context.method,
        requested_route=context.requested_route,
        key=context.key,
        fingerprint=fingerprint,
    )
    assert writer.completed == []


@pytest.mark.asyncio
async def test_in_progress_retry_reports_original_identity_and_delay() -> None:
    writer = MockOperationReservations(replace(NEW, created=False))
    with pytest.raises(IdempotencyInProgressError) as caught:
        await IdempotencyService(writer).find_or_reserve(
            context=CONTEXT,
            access=ACCESS,
            authorization=AUTHORIZATION,
            fingerprint=RequestFingerprint(REQUEST.fingerprint),
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
    assert caught.value.operation_id == NEW.operation_id
    assert caught.value.retry_after_seconds == 3


@pytest.mark.asyncio
async def test_uncertain_outcome_is_returned_without_completing_or_restarting() -> None:
    """The owner must decide how to present uncertainty about the original operation."""
    saved = replace(NEW, created=False, state=OperationReservationState.RECOVERY_REQUIRED)
    writer = MockOperationReservations(saved)
    assert await IdempotencyService(writer).find_or_reserve(
        context=CONTEXT,
        access=ACCESS,
        authorization=AUTHORIZATION,
        fingerprint=RequestFingerprint(REQUEST.fingerprint),
        expected_replay_kind=OperationReplayKind.SAFE_RESULT,
    ) == RecoveryRequiredOperationDTO(saved.operation_id)
    assert writer.completed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(OperationReplayKind))
async def test_matching_replay_keeps_original_deadline(kind: OperationReplayKind) -> None:
    saved = replace(
        NEW,
        created=False,
        state=OperationReservationState.REPLAYABLE,
        replay_kind=kind,
        expires_at=None if kind is OperationReplayKind.ASYNC_JOB else EXPIRY,
    )
    writer = MockOperationReservations(saved)
    result = await IdempotencyService(writer).find_or_reserve(
        context=CONTEXT,
        access=ACCESS,
        authorization=AUTHORIZATION,
        fingerprint=RequestFingerprint(REQUEST.fingerprint),
        expected_replay_kind=kind,
    )
    assert isinstance(result, (CompletedSynchronousOperationDTO, AcceptedAsyncOperationDTO))
    assert result.operation_id == saved.operation_id
    assert result.created is False
    assert result.expires_at == saved.expires_at
    if kind is OperationReplayKind.ASYNC_JOB:
        assert isinstance(result, AcceptedAsyncOperationDTO)
    else:
        assert isinstance(result, CompletedSynchronousOperationDTO)
        assert result.replay_kind is kind
    assert writer.completed == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "saved",
    [
        replace(NEW, state=OperationReservationState.REPLAYABLE),
        replace(NEW, state=OperationReservationState.RECOVERY_REQUIRED),
        replace(NEW, created=False, replay_kind=OperationReplayKind.SAFE_RESULT),
        replace(NEW, created=False, expires_at=EXPIRY),
        replace(
            NEW,
            created=False,
            state=OperationReservationState.RECOVERY_REQUIRED,
            replay_kind=OperationReplayKind.SAFE_RESULT,
        ),
        replace(
            NEW, created=False, state=OperationReservationState.RECOVERY_REQUIRED, expires_at=EXPIRY
        ),
        replace(
            NEW,
            created=False,
            state=OperationReservationState.REPLAYABLE,
            replay_kind=OperationReplayKind.ASYNC_JOB,
        ),
        replace(NEW, expires_at=EXPIRY),
        replace(NEW, replay_kind=OperationReplayKind.SAFE_RESULT),
        replace(NEW, created=False, state=OperationReservationState.REPLAYABLE),
        replace(
            NEW,
            created=False,
            state=OperationReservationState.REPLAYABLE,
            replay_kind=OperationReplayKind.SAFE_RESULT,
        ),
        replace(
            NEW,
            created=False,
            state=OperationReservationState.REPLAYABLE,
            replay_kind=OperationReplayKind.ANSWER_RECEIPT,
            expires_at=EXPIRY,
        ),
    ],
)
async def test_incompatible_reservation_cannot_be_treated_as_success(
    saved: OperationReservationResultDTO,
) -> None:
    with pytest.raises(ConflictError):
        await IdempotencyService(MockOperationReservations(saved)).find_or_reserve(
            context=CONTEXT,
            access=ACCESS,
            authorization=AUTHORIZATION,
            fingerprint=RequestFingerprint(REQUEST.fingerprint),
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", list(OperationReplayKind))
async def test_completion_records_only_safe_replay_metadata(kind: OperationReplayKind) -> None:
    writer = MockOperationReservations()
    writer.expiry = None if kind is OperationReplayKind.ASYNC_JOB else EXPIRY
    result = await IdempotencyService(writer).record_completed_result(
        NewOperationReservationDTO(NEW.operation_id), replay_kind=kind
    )
    assert result.operation_id == NEW.operation_id
    assert result.created is True
    assert result.expires_at == writer.expiry
    if kind is OperationReplayKind.ASYNC_JOB:
        assert isinstance(result, AcceptedAsyncOperationDTO)
    else:
        assert isinstance(result, CompletedSynchronousOperationDTO)
        assert result.replay_kind is kind
    assert writer.completed == [(NEW.operation_id, kind)]


@pytest.mark.asyncio
async def test_synchronous_completion_requires_a_stored_expiry() -> None:
    writer = MockOperationReservations()
    writer.expiry = None
    with pytest.raises(ConflictError):
        await IdempotencyService(writer).record_completed_result(
            NewOperationReservationDTO(NEW.operation_id),
            replay_kind=OperationReplayKind.SAFE_RESULT,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "operation",
    [
        replace(NEW, created=False),
        replace(NEW, state=OperationReservationState.REPLAYABLE),
        replace(NEW, replay_kind=OperationReplayKind.SAFE_RESULT),
        replace(NEW, expires_at=EXPIRY),
    ],
)
async def test_completion_cannot_change_previously_reserved_or_finished_work(
    operation: OperationReservationResultDTO,
) -> None:
    writer = MockOperationReservations()
    with pytest.raises(ConflictError):
        await IdempotencyService(writer).record_completed_result(
            # Deliberately bypass static typing to reject legacy storage projections at runtime.
            cast(NewOperationReservationDTO, operation),
            replay_kind=OperationReplayKind.SAFE_RESULT,
        )
    assert writer.completed == []


@pytest.mark.asyncio
async def test_changed_request_conflict_propagates_without_a_new_operation() -> None:
    writer = MockOperationReservations()
    writer.error = IdempotencyKeyReusedError()
    with pytest.raises(IdempotencyKeyReusedError):
        await IdempotencyService(writer).find_or_reserve(
            context=CONTEXT,
            access=ACCESS,
            authorization=AUTHORIZATION,
            fingerprint=RequestFingerprint(REQUEST.fingerprint),
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
    assert writer.completed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("expiry", [None, EXPIRY])
async def test_async_replay_and_completion_preserve_optional_expiry(
    expiry: datetime | None,
) -> None:
    """An asynchronous acceptance keeps its saved deadline, including no deadline."""
    saved = replace(
        NEW,
        created=False,
        state=OperationReservationState.REPLAYABLE,
        replay_kind=OperationReplayKind.ASYNC_JOB,
        expires_at=expiry,
    )
    writer = MockOperationReservations(saved)
    replay = await IdempotencyService(writer).find_or_reserve(
        context=CONTEXT,
        access=ACCESS,
        authorization=AUTHORIZATION,
        fingerprint=RequestFingerprint(REQUEST.fingerprint),
        expected_replay_kind=OperationReplayKind.ASYNC_JOB,
    )
    assert replay == AcceptedAsyncOperationDTO(NEW.operation_id, False, expiry)
    writer.expiry = expiry
    completed = await IdempotencyService(writer).record_completed_result(
        NewOperationReservationDTO(NEW.operation_id), replay_kind=OperationReplayKind.ASYNC_JOB
    )
    assert completed == AcceptedAsyncOperationDTO(NEW.operation_id, True, expiry)


@pytest.mark.asyncio
async def test_wrong_expected_kind_cannot_replay_a_completed_synchronous_result() -> None:
    saved = replace(
        NEW,
        created=False,
        state=OperationReservationState.REPLAYABLE,
        replay_kind=OperationReplayKind.SAFE_RESULT,
        expires_at=EXPIRY,
    )
    writer = MockOperationReservations(saved)
    with pytest.raises(ConflictError):
        await IdempotencyService(writer).find_or_reserve(
            context=CONTEXT,
            access=ACCESS,
            authorization=AUTHORIZATION,
            fingerprint=RequestFingerprint(REQUEST.fingerprint),
            expected_replay_kind=OperationReplayKind.ASYNC_JOB,
        )
    assert writer.completed == []


@pytest.mark.asyncio
async def test_completion_failure_propagates_without_retry() -> None:
    writer = MockOperationReservations()
    writer.error = RuntimeError("completion unavailable")
    with pytest.raises(RuntimeError, match="completion unavailable"):
        await IdempotencyService(writer).record_completed_result(
            NewOperationReservationDTO(NEW.operation_id),
            replay_kind=OperationReplayKind.SAFE_RESULT,
        )
    assert writer.completed == [(NEW.operation_id, OperationReplayKind.SAFE_RESULT)]
