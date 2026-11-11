"""Recover content-free Project status from complete saved identity after ordinary history expires."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import ACTOR_ID, ORGANIZATION_ID, PROJECT_ID

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.deletion_recovery_authorization_dto import (
    DeletionRecoveryAuthorizationDTO,
)
from inframeld_backend.access.application.protocols.deletion_recovery_authorizer import (
    DeletionRecoveryAuthorizer,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.deletion_status_lookup import (
    DeletionStatusLookup,
)
from inframeld_backend.shared.application.protocols.project_deletion_binding_reader import (
    ProjectDeletionBindingReader,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.project_deletion_lookup_service import (
    ProjectDeletionLookupService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ACCESS = AccessContextDTO(
    ACTOR_ID,
    MockAuthenticationEvidence.browser(
        installation_id=InstallationId(UUID(int=20)), version=HumanCredentialVersion(1)
    ),
)
AUTH = DeletionRecoveryAuthorizationDTO(
    InstallationId(UUID(int=20)), ORGANIZATION_ID, ACCESS.actor_principal_id
)
QUERY = LookupOriginalOperationQuery(
    AUTH.installation_id,
    ORGANIZATION_ID,
    PROJECT_ID,
    HttpMethod.DELETE,
    f"/v1/projects/{PROJECT_ID.value}",
    IdempotencyKey("lost-first-response"),
    OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_DELETION, ActionId("delete-project")
    ),
)
OPERATION = OperationId("original-project-deletion")
RETAINED = RetainedDeletionStatusDTO(
    operation_id=OPERATION,
    job_status=None,
    admission_confirmed=True,
    access_blocked=True,
    application_shutdown_complete=None,
    physical_cleanup_complete=True,
    expires_at=datetime(2030, 1, 1, tzinfo=UTC),
)


class MockAuthorizer(DeletionRecoveryAuthorizer):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: Exception | None = None

    @override
    async def require_current_human(
        self, *, access: AccessContextDTO
    ) -> DeletionRecoveryAuthorizationDTO:
        self.events.append("authorize")
        if self.error is not None:
            raise self.error
        return AUTH


class MockBindings(ProjectDeletionBindingReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.operation: OperationId | None = OPERATION

    @override
    async def find(
        self,
        *,
        authorization: DeletionRecoveryAuthorizationDTO,
        query: LookupOriginalOperationQuery,
    ) -> OperationId | None:
        self.events.append("binding")
        assert authorization == AUTH and query == QUERY
        return self.operation


class MockStatus(DeletionStatusLookup):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: RetainedDeletionStatusDTO | UnresolvedOperationDTO = RETAINED
        self.error: Exception | None = None

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: GetDeletionStatusQuery
    ) -> RetainedDeletionStatusDTO | UnresolvedOperationDTO:
        self.events.append("status")
        assert query.operation_id == OPERATION
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_saved_identity_finds_original_status_without_ordinary_reservation_or_receipt() -> (
    None
):
    events: list[str] = []
    result = await ProjectDeletionLookupService(
        MockAuthorizer(events), MockBindings(events), MockStatus(events)
    ).lookup(access=ACCESS, query=QUERY)
    assert result == RETAINED and events == ["authorize", "binding", "status"]


@pytest.mark.asyncio
async def test_current_eligibility_precedes_all_history() -> None:
    events: list[str] = []
    auth = MockAuthorizer(events)
    auth.error = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await ProjectDeletionLookupService(auth, MockBindings(events), MockStatus(events)).lookup(
            access=ACCESS, query=QUERY
        )
    assert events == ["authorize"]


@pytest.mark.asyncio
async def test_wrong_saved_scope_and_missing_or_expired_history_are_uniformly_unresolved() -> None:
    events: list[str] = []
    bindings, status = MockBindings(events), MockStatus(events)
    service = ProjectDeletionLookupService(MockAuthorizer(events), bindings, status)
    result = await service.lookup(
        access=ACCESS, query=replace(QUERY, organization_id=OrganizationId(UUID(int=100)))
    )
    assert isinstance(result, UnresolvedOperationDTO) and events == ["authorize"]
    bindings.operation = None
    assert isinstance(await service.lookup(access=ACCESS, query=QUERY), UnresolvedOperationDTO)
    assert events == ["authorize", "authorize", "binding"]
    bindings.operation = OPERATION
    status.result = UnresolvedOperationDTO()
    assert isinstance(await service.lookup(access=ACCESS, query=QUERY), UnresolvedOperationDTO)


@pytest.mark.asyncio
async def test_inconsistent_status_is_not_reinterpreted_as_completion_or_absence() -> None:
    events: list[str] = []
    status = MockStatus(events)
    status.error = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await ProjectDeletionLookupService(
            MockAuthorizer(events), MockBindings(events), status
        ).lookup(access=ACCESS, query=QUERY)
    assert events == ["authorize", "binding", "status"]
