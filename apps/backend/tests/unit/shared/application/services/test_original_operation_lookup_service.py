"""Observe original admission without disclosing history before current authorization."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.operation_lookup_authorization_dto import (
    OperationLookupAuthorizationDTO,
)
from inframeld_backend.access.application.protocols.operation_lookup_authorizer import (
    OperationLookupAuthorizer,
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
from inframeld_backend.shared.application.dtos.in_progress_operation_dto import (
    InProgressOperationDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import (
    OperationReplayKind,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
)
from inframeld_backend.shared.application.protocols.operation_lookup_reader import (
    OperationLookupReader,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.original_operation_lookup_service import (
    OriginalOperationLookupService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ACCESS = AccessContextDTO(PrincipalId(UUID(int=1)), MockAuthenticationEvidence.browser())
QUERY = LookupOriginalOperationQuery(
    InstallationId(UUID(int=2)),
    OrganizationId(UUID(int=3)),
    ProjectId(UUID(int=4)),
    "POST",
    "/v1/projects/{project_id}/grants",
    IdempotencyKey("lost-ack"),
    OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ActionId("create-access-groups")
    ),
)
EXPIRY = datetime(2030, 1, 1, tzinfo=UTC)
SAVED = OperationReservationResultDTO(
    OperationId("original-operation"),
    False,
    OperationReservationState.REPLAYABLE,
    OperationReplayKind.SAFE_RESULT,
    EXPIRY,
)


class MockLookupAuthorizer(OperationLookupAuthorizer):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.failure: Exception | None = None
        self.scope = OperationLookupAuthorizationDTO(QUERY.organization_id, QUERY.project_id)

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: LookupOriginalOperationQuery
    ) -> OperationLookupAuthorizationDTO:
        self.events.append("authorize")
        assert access == ACCESS
        assert request == QUERY
        if self.failure is not None:
            raise self.failure
        return self.scope


class MockLookupReader(OperationLookupReader):
    def __init__(self, events: list[str], saved: OperationReservationResultDTO | None) -> None:
        self.events = events
        self.saved = saved
        self.failure: Exception | None = None

    @override
    async def read(
        self, *, principal_id: PrincipalId, query: LookupOriginalOperationQuery
    ) -> OperationReservationResultDTO | None:
        self.events.append("read")
        assert principal_id == ACCESS.actor_principal_id
        assert query == QUERY
        if self.failure is not None:
            raise self.failure
        return self.saved


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "saved",
    [
        None,
        SAVED,
        replace(
            SAVED,
            state=OperationReservationState.RECOVERY_REQUIRED,
            replay_kind=None,
            expires_at=None,
        ),
    ],
)
async def test_denial_precedes_search_for_every_history(
    saved: OperationReservationResultDTO | None,
) -> None:
    events: list[str] = []
    authorizer = MockLookupAuthorizer(events)
    authorizer.failure = AccessDeniedError()
    service = OriginalOperationLookupService(authorizer, MockLookupReader(events, saved))
    with pytest.raises(AccessDeniedError):
        await service.lookup(access=ACCESS, query=QUERY)
    assert events == ["authorize"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "saved, expected",
    [
        (None, UnresolvedOperationDTO()),
        (
            SAVED,
            CompletedSynchronousOperationDTO(
                SAVED.operation_id, False, OperationReplayKind.SAFE_RESULT, EXPIRY
            ),
        ),
        (
            replace(SAVED, replay_kind=OperationReplayKind.ASYNC_JOB, expires_at=None),
            AcceptedAsyncOperationDTO(SAVED.operation_id, False, None),
        ),
        (
            replace(SAVED, replay_kind=OperationReplayKind.ASYNC_JOB),
            AcceptedAsyncOperationDTO(SAVED.operation_id, False, EXPIRY),
        ),
        (
            replace(
                SAVED,
                state=OperationReservationState.IN_PROGRESS,
                replay_kind=None,
                expires_at=None,
            ),
            InProgressOperationDTO(SAVED.operation_id),
        ),
        (
            replace(
                SAVED,
                state=OperationReservationState.RECOVERY_REQUIRED,
                replay_kind=None,
                expires_at=None,
            ),
            RecoveryRequiredOperationDTO(SAVED.operation_id),
        ),
    ],
)
async def test_lookup_preserves_retained_classification(
    saved: OperationReservationResultDTO | None, expected: object
) -> None:
    events: list[str] = []
    result = await OriginalOperationLookupService(
        MockLookupAuthorizer(events), MockLookupReader(events, saved)
    ).lookup(access=ACCESS, query=QUERY)
    assert result == expected
    assert events == ["authorize", "read"]


@pytest.mark.asyncio
async def test_wrong_authorized_scope_stops_before_history() -> None:
    events: list[str] = []
    authorizer = MockLookupAuthorizer(events)
    authorizer.scope = replace(authorizer.scope, project_id=ProjectId(UUID(int=99)))
    with pytest.raises(RuntimeError):
        await OriginalOperationLookupService(authorizer, MockLookupReader(events, SAVED)).lookup(
            access=ACCESS, query=QUERY
        )
    assert events == ["authorize"]


@pytest.mark.asyncio
async def test_grant_route_cannot_use_a_weaker_guard() -> None:
    events: list[str] = []
    query = replace(
        QUERY,
        expected_authority=OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("create-access-groups")
        ),
    )
    with pytest.raises(InvalidInputError):
        await OriginalOperationLookupService(
            MockLookupAuthorizer(events), MockLookupReader(events, SAVED)
        ).lookup(access=ACCESS, query=query)
    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "saved",
    [
        replace(SAVED, expires_at=None),
        replace(SAVED, state=OperationReservationState.IN_PROGRESS),
        replace(SAVED, state=OperationReservationState.RECOVERY_REQUIRED),
        replace(SAVED, created=True),
        replace(SAVED, replay_kind=None),
    ],
)
async def test_malformed_authorized_outcome_is_a_failure(
    saved: OperationReservationResultDTO,
) -> None:
    events: list[str] = []
    with pytest.raises(DependencyUnavailableError):
        await OriginalOperationLookupService(
            MockLookupAuthorizer(events), MockLookupReader(events, saved)
        ).lookup(access=ACCESS, query=QUERY)


@pytest.mark.asyncio
async def test_timeout_is_not_a_successful_unresolved_observation() -> None:
    events: list[str] = []
    reader = MockLookupReader(events, None)
    reader.failure = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await OriginalOperationLookupService(MockLookupAuthorizer(events), reader).lookup(
            access=ACCESS, query=QUERY
        )
    assert events == ["authorize", "read"]
