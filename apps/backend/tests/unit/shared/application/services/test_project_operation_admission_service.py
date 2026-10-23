from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.action_authorizer import ActionAuthorizer
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
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
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    IdempotencyInProgressError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.services.project_operation_admission_service import (
    ProjectOperationAdmissionService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)

ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)))
ORGANIZATION = OrganizationId(UUID(int=2))
ACTION = ActionId("create-access-groups")
OPERATION = OperationId("original-admission")
REQUEST = ProjectOperationAdmissionRequestDTO(
    project_id=ProjectId(UUID(int=3)),
    method="POST",
    requested_route="/v1/projects/{project_id}/builds",
    key=IdempotencyKey("same-admission"),
    fingerprint=RequestFingerprint(b"F" * 32),
)

AUTHORIZATION = ProjectActionAuthorizationDTO(ORGANIZATION, REQUEST.project_id)


class MockActionAuthorizer(ActionAuthorizer):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: AccessDeniedError | ResourceNotFoundError | None = None
        self.result = AUTHORIZATION

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectActionAuthorizationRequestDTO
    ) -> ProjectActionAuthorizationDTO:
        self.events.append("authorize")
        assert access == ACCESS
        assert request.action_id == ACTION
        assert request.project_id == REQUEST.project_id
        if self.error is not None:
            raise self.error
        return self.result


class MockOperationIdempotency(OperationIdempotency):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: (
            NewOperationReservationDTO
            | CompletedSynchronousOperationDTO
            | AcceptedAsyncOperationDTO
            | RecoveryRequiredOperationDTO
        ) = NewOperationReservationDTO(OPERATION)
        self.error: Exception | None = None
        self.calls = 0
        self.context: OperationAdmissionContextDTO | None = None
        self.access: AccessContextDTO | None = None
        self.authorization: object | None = None
        self.fingerprint: RequestFingerprint | None = None
        self.expected_kind: OperationReplayKind | None = None

    @override
    async def find_or_reserve[ProjectScope: ProjectId | None](
        self,
        *,
        context: OperationAdmissionContextDTO,
        access: AccessContextDTO,
        authorization: AuthorizedOperationScope[ProjectScope],
        fingerprint: RequestFingerprint,
        expected_replay_kind: OperationReplayKind,
    ) -> (
        NewOperationReservationDTO
        | CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO
    ):
        self.events.append("reserve")
        self.calls += 1
        self.context = context
        self.access = access
        self.authorization = authorization
        self.fingerprint = fingerprint
        self.expected_kind = expected_replay_kind
        if self.error is not None:
            raise self.error
        return self.result

    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        raise AssertionError("Admission alone must not complete the owning workflow.")


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [AccessDeniedError, ResourceNotFoundError])
async def test_denied_access_never_inspects_a_saved_operation(
    error_type: type[AccessDeniedError | ResourceNotFoundError],
) -> None:
    events: list[str] = []
    authorizer = MockActionAuthorizer(events)
    authorizer.error = error_type()
    idempotency = MockOperationIdempotency(events)
    with pytest.raises(error_type):
        await ProjectOperationAdmissionService(authorizer, idempotency).reserve(
            access=ACCESS,
            action_id=ACTION,
            request=REQUEST,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
    assert idempotency.calls == 0
    assert events == ["authorize"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        NewOperationReservationDTO(OPERATION),
        CompletedSynchronousOperationDTO(
            OPERATION, False, OperationReplayKind.SAFE_RESULT, datetime(2030, 1, 1, tzinfo=UTC)
        ),
    ],
    ids=["new", "replay"],
)
async def test_mismatched_scope_stops_before_reservation_or_replay(
    outcome: NewOperationReservationDTO | CompletedSynchronousOperationDTO,
) -> None:
    """A broken authorizer must not reserve or disclose work for another project."""
    events: list[str] = []
    authorizer = MockActionAuthorizer(events)
    authorizer.result = replace(AUTHORIZATION, project_id=ProjectId(UUID(int=4)))
    idempotency = MockOperationIdempotency(events)
    idempotency.result = outcome

    with pytest.raises(RuntimeError, match="Authorization returned a different project"):
        await ProjectOperationAdmissionService(authorizer, idempotency).reserve(
            access=ACCESS,
            action_id=ACTION,
            request=REQUEST,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )

    assert idempotency.calls == 0
    assert events == ["authorize"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome, kind",
    [
        (NewOperationReservationDTO(OPERATION), OperationReplayKind.SAFE_RESULT),
        (
            CompletedSynchronousOperationDTO(
                OPERATION, False, OperationReplayKind.SAFE_RESULT, datetime(2030, 1, 1, tzinfo=UTC)
            ),
            OperationReplayKind.SAFE_RESULT,
        ),
        (AcceptedAsyncOperationDTO(OPERATION, False, None), OperationReplayKind.ASYNC_JOB),
        (RecoveryRequiredOperationDTO(OPERATION), OperationReplayKind.SAFE_RESULT),
    ],
)
async def test_admission_passes_trusted_scope_and_preserves_the_outcome(
    outcome: NewOperationReservationDTO
    | CompletedSynchronousOperationDTO
    | AcceptedAsyncOperationDTO
    | RecoveryRequiredOperationDTO,
    kind: OperationReplayKind,
) -> None:
    events: list[str] = []
    idempotency = MockOperationIdempotency(events)
    idempotency.result = outcome
    result = await ProjectOperationAdmissionService(
        MockActionAuthorizer(events), idempotency
    ).reserve(access=ACCESS, action_id=ACTION, request=REQUEST, expected_replay_kind=kind)
    assert result == outcome
    assert idempotency.expected_kind is kind
    assert idempotency.context == OperationAdmissionContextDTO(
        method=REQUEST.method, requested_route=REQUEST.requested_route, key=REQUEST.key
    )
    assert idempotency.access is ACCESS
    assert idempotency.authorization is AUTHORIZATION
    assert idempotency.fingerprint == REQUEST.fingerprint
    assert events == ["authorize", "reserve"]


@pytest.mark.asyncio
async def test_a_prior_success_does_not_cache_authorization() -> None:
    events: list[str] = []
    authorizer = MockActionAuthorizer(events)
    idempotency = MockOperationIdempotency(events)
    idempotency.result = CompletedSynchronousOperationDTO(
        OPERATION, False, OperationReplayKind.SAFE_RESULT, datetime(2030, 1, 1, tzinfo=UTC)
    )
    service = ProjectOperationAdmissionService(authorizer, idempotency)
    assert (
        await service.reserve(
            access=ACCESS,
            action_id=ACTION,
            request=REQUEST,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        == idempotency.result
    )
    authorizer.error = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await service.reserve(
            access=ACCESS,
            action_id=ACTION,
            request=REQUEST,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
    assert idempotency.calls == 1
    assert events == ["authorize", "reserve", "authorize"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error", [IdempotencyInProgressError(OPERATION, 3), ConflictError("unexpected replay outcome")]
)
async def test_shared_retry_errors_propagate_without_another_attempt(error: ConflictError) -> None:
    events: list[str] = []
    idempotency = MockOperationIdempotency(events)
    idempotency.error = error
    with pytest.raises(type(error)) as caught:
        await ProjectOperationAdmissionService(MockActionAuthorizer(events), idempotency).reserve(
            access=ACCESS,
            action_id=ACTION,
            request=REQUEST,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
    assert caught.value is error
    assert idempotency.calls == 1
