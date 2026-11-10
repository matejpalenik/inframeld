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
from inframeld_backend.shared.application.dtos.accepted_operation_lookup_dto import (
    AcceptedOperationLookupDTO,
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
from inframeld_backend.shared.application.dtos.original_operation_lookup_record_dto import (
    OriginalOperationLookupRecordDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
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
from inframeld_backend.shared.application.protocols.original_operation_lookup import (
    OriginalOperationLookup,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.original_operation_lookup_service import (
    OriginalOperationLookupService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_id import JobId
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
    HttpMethod.POST,
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
        self.query = QUERY

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: LookupOriginalOperationQuery
    ) -> OperationLookupAuthorizationDTO:
        self.events.append("authorize")
        assert access == ACCESS
        assert request == self.query
        if self.failure is not None:
            raise self.failure
        return self.scope


class MockLookupReader(OperationLookupReader):
    def __init__(self, events: list[str], saved: OperationReservationResultDTO | None) -> None:
        self.events = events
        self.saved = saved
        self.failure: Exception | None = None
        self.job_id: JobId | None = None
        self.query = QUERY

    @override
    async def read(
        self, *, principal_id: PrincipalId, query: LookupOriginalOperationQuery
    ) -> OriginalOperationLookupRecordDTO | None:
        self.events.append("read")
        assert principal_id == ACCESS.actor_principal_id
        assert query == self.query
        if self.failure is not None:
            raise self.failure
        return (
            OriginalOperationLookupRecordDTO(self.saved, self.job_id)
            if self.saved is not None
            else None
        )


@pytest.mark.asyncio
async def test_organization_lookup_preserves_original_identity_after_current_authorization() -> (
    None
):
    query = replace(
        QUERY,
        project_id=None,
        method=HttpMethod.PUT,
        requested_route=f"/v1/organizations/{QUERY.organization_id.value}/grants/{UUID(int=9)}/create-projects",
        expected_authority=OperationLookupAuthority(
            family=OperationLookupAuthorityFamily.ORGANIZATION_GRANT_READ,
            action_id=ActionId("create-projects"),
        ),
    )
    events: list[str] = []
    authorizer = MockLookupAuthorizer(events)
    authorizer.query = query
    authorizer.scope = OperationLookupAuthorizationDTO(query.organization_id, None)
    reader = MockLookupReader(events, SAVED)
    reader.query = query
    result = await OriginalOperationLookupService(authorizer, reader).lookup(
        access=ACCESS, query=query
    )
    assert isinstance(result, CompletedSynchronousOperationDTO)
    assert result.operation_id == SAVED.operation_id and result.expires_at == SAVED.expires_at
    assert events == ["authorize", "read"]


@pytest.mark.asyncio
async def test_lookup_preserves_established_job_reference_without_execution_facts() -> None:
    events: list[str] = []
    query = replace(
        QUERY,
        requested_route="/v1/original-project-operation",
        expected_authority=OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_ACTION_USE, QUERY.expected_authority.action_id
        ),
    )
    authorizer = MockLookupAuthorizer(events)
    authorizer.query = query
    reader = MockLookupReader(
        events, replace(SAVED, replay_kind=OperationReplayKind.ASYNC_JOB, expires_at=None)
    )
    reader.job_id = JobId(UUID(int=8))
    reader.query = query
    result = await OriginalOperationLookupService(authorizer, reader).lookup(
        access=ACCESS, query=query
    )
    assert result == AcceptedOperationLookupDTO(SAVED.operation_id, None, reader.job_id)
    assert events == ["authorize", "read"]


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
            AcceptedOperationLookupDTO(SAVED.operation_id, None),
        ),
        (
            replace(SAVED, replay_kind=OperationReplayKind.ASYNC_JOB),
            AcceptedOperationLookupDTO(SAVED.operation_id, EXPIRY),
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


class MockProjectDeletionLookup(OriginalOperationLookup):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> UnresolvedOperationDTO:
        assert access == ACCESS
        self.events.append("project-deletion")
        return UnresolvedOperationDTO()


@pytest.mark.asyncio
async def test_project_deletion_lookup_dispatch_never_uses_ordinary_authorizer() -> None:
    events: list[str] = []
    query = replace(
        QUERY,
        method=HttpMethod.DELETE,
        requested_route=f"/v1/projects/{UUID(int=4)}",
        expected_authority=OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_DELETION, ActionId("delete-project")
        ),
    )
    result = await OriginalOperationLookupService(
        MockLookupAuthorizer(events),
        MockLookupReader(events, SAVED),
        project_deletion_lookup=MockProjectDeletionLookup(events),
    ).lookup(access=ACCESS, query=query)
    assert isinstance(result, UnresolvedOperationDTO)
    assert events == ["project-deletion"]


@pytest.mark.asyncio
async def test_unconfigured_project_deletion_lookup_is_unavailable_not_ordinary_replay() -> None:
    events: list[str] = []
    query = replace(
        QUERY,
        method=HttpMethod.DELETE,
        requested_route=f"/v1/projects/{UUID(int=4)}",
        expected_authority=OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_DELETION, ActionId("delete-project")
        ),
    )
    with pytest.raises(DependencyUnavailableError):
        await OriginalOperationLookupService(
            MockLookupAuthorizer(events), MockLookupReader(events, SAVED)
        ).lookup(access=ACCESS, query=query)
    assert events == []
