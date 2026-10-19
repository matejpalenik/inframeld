from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.protocols.project_grant_change_writer import (
    ProjectGrantChangeWriter,
)
from inframeld_backend.access.application.services.project_grant_change_service import (
    ProjectGrantChangeService,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.project_operation_admission_request_dto import (
    ProjectOperationAdmissionRequestDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_reservation_writer import (
    OperationReservationWriter,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId

ACTOR_ID = PrincipalId(UUID(int=1))
RECIPIENT_ID = PrincipalId(UUID(int=2))
ORGANIZATION_ID = OrganizationId(UUID(int=3))
PROJECT_ID = ProjectId(UUID(int=4))
ACTION_ID = ActionId("create-access-groups")
ACCESS = AccessContextDTO(actor_principal_id=ACTOR_ID)

AUTHORIZATION = ProjectGrantAuthorizationDTO(
    organization_id=ORGANIZATION_ID,
    project_access_revision=7,
)

REQUEST = ProjectOperationAdmissionRequestDTO(
    project_id=PROJECT_ID,
    method="POST",
    requested_route="/v1/projects/{project_id}/grants",
    key=IdempotencyKey("assign-bob-1"),
    fingerprint=b"x" * 32,
)

SAVED_RESULT = OperationReservationResultDTO(
    operation_id=OperationId("saved-grant"),
    created=False,
    state=OperationReservationState.REPLAYABLE,
    replay_kind=OperationReplayKind.SAFE_RESULT,
    expires_at=datetime(2030, 1, 1, tzinfo=UTC),
)

NEW_RESERVATION = replace(
    SAVED_RESULT,
    created=True,
    state=OperationReservationState.IN_PROGRESS,
    replay_kind=None,
    expires_at=None,
)


class MockProjectGrantAuthorizer(ProjectGrantAuthorizer):
    """Allow the first attempt and support changed authority on a later attempt."""

    def __init__(self) -> None:
        self.error: AccessDeniedError | ResourceNotFoundError | None = None
        self.calls = 0
        self.last_request: tuple[AccessContextDTO, ProjectId, PrincipalId, ActionId] | None = None

    @override
    async def require_use_only_assignment(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantAuthorizationDTO:
        self.calls += 1
        self.last_request = (
            access,
            project_id,
            recipient_principal_id,
            action_id,
        )
        if self.error is not None:
            raise self.error
        return AUTHORIZATION


class MockOperationReservations(OperationReservationWriter):
    """Supply a reservation for cases that must not complete a new grant."""

    def __init__(self, result: OperationReservationResultDTO) -> None:
        self._result = result
        self.calls = 0
        self.last_request: OperationReservationRequestDTO | None = None

    @override
    async def reserve(
        self,
        request: OperationReservationRequestDTO,
    ) -> OperationReservationResultDTO:
        self.calls += 1
        self.last_request = request
        return self._result

    @override
    async def mark_replayable(
        self,
        operation_id: OperationId,
        replay_kind: OperationReplayKind,
    ) -> datetime | None:
        raise AssertionError("These cases must not complete a new grant.")


class MockUnexpectedGrantChanges(ProjectGrantChangeWriter):
    @override
    async def create_use_only(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
        expected_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        raise AssertionError("These cases must not write a grant.")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error_type",
    [AccessDeniedError, ResourceNotFoundError],
)
async def test_denied_authorization_does_not_reserve_work(
    error_type: type[AccessDeniedError | ResourceNotFoundError],
) -> None:
    """Authorization failure must stop the workflow before any reservation."""
    authorizer = MockProjectGrantAuthorizer()
    authorizer.error = error_type()
    reservations = MockOperationReservations(SAVED_RESULT)
    service = ProjectGrantChangeService(
        authorizer,
        reservations,
        MockUnexpectedGrantChanges(),
    )

    with pytest.raises(error_type):
        await service.assign_use_only(
            access=ACCESS,
            request=REQUEST,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=7,
        )

    assert reservations.calls == 0


@pytest.mark.asyncio
async def test_replay_rechecks_authorization_before_returning_saved_result() -> None:
    """A prior success cannot bypass changed authority on the next request."""
    authorizer = MockProjectGrantAuthorizer()
    reservations = MockOperationReservations(SAVED_RESULT)
    service = ProjectGrantChangeService(
        authorizer,
        reservations,
        MockUnexpectedGrantChanges(),
    )

    first = await service.assign_use_only(
        access=ACCESS,
        request=REQUEST,
        recipient_principal_id=RECIPIENT_ID,
        action_id=ACTION_ID,
        expected_access_revision=0,
    )

    assert first == SAVED_RESULT
    assert authorizer.last_request == (
        ACCESS,
        PROJECT_ID,
        RECIPIENT_ID,
        ACTION_ID,
    )
    assert reservations.last_request == OperationReservationRequestDTO(
        principal_id=ACTOR_ID,
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        method=REQUEST.method,
        requested_route=REQUEST.requested_route,
        key=REQUEST.key,
        fingerprint=REQUEST.fingerprint,
    )

    authorizer.error = AccessDeniedError()

    with pytest.raises(AccessDeniedError):
        await service.assign_use_only(
            access=ACCESS,
            request=REQUEST,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=0,
        )

    assert authorizer.calls == 2
    assert reservations.calls == 1


@pytest.mark.asyncio
async def test_new_work_rejects_a_stale_revision_before_writing_grant() -> None:
    """New assignments must match the revision established by authorization."""
    reservations = MockOperationReservations(NEW_RESERVATION)
    service = ProjectGrantChangeService(
        MockProjectGrantAuthorizer(),
        reservations,
        MockUnexpectedGrantChanges(),
    )

    with pytest.raises(StaleRevisionError):
        await service.assign_use_only(
            access=ACCESS,
            request=REQUEST,
            recipient_principal_id=RECIPIENT_ID,
            action_id=ACTION_ID,
            expected_access_revision=0,
        )

    assert reservations.calls == 1
