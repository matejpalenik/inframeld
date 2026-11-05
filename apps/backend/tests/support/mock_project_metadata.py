from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import override
from uuid import UUID

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_authorization_facts_dto import (
    ProjectMetadataAuthorizationFactsDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.application.protocols.project_metadata_authorizer import (
    ProjectMetadataAuthorizer,
)
from inframeld_backend.access.application.protocols.project_metadata_facts_reader import (
    ProjectMetadataFactsReader,
)
from inframeld_backend.access.application.protocols.project_metadata_repository import (
    ProjectMetadataRepository,
)
from inframeld_backend.access.domain.entities.project_metadata import ProjectMetadata
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.dtos.resource_name_binding_dto import (
    ResourceNameBindingDTO,
)
from inframeld_backend.shared.application.dtos.resource_name_scope_dto import ResourceNameScopeDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.resource_name_binding_reader import (
    ResourceNameBindingReader,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.queries.resolve_resource_name_query import (
    ResolveResourceNameQuery,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from tests.support.authentication_evidence import MockAuthenticationEvidence

ACTOR_ID = PrincipalId(UUID(int=1))

ORGANIZATION_ID = OrganizationId(UUID(int=2))

PROJECT_ID = ProjectId(UUID(int=3))

ACCESS = AccessContextDTO(ACTOR_ID, MockAuthenticationEvidence.browser())

SAVED_RESULT = CompletedSynchronousOperationDTO(
    OperationId("metadata-original"),
    False,
    OperationReplayKind.SAFE_RESULT,
    datetime(2030, 1, 1, tzinfo=UTC),
)

NEW_RESERVATION = NewOperationReservationDTO(SAVED_RESULT.operation_id)


class MockTransactions(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: Exception | None = None

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
            if self.error is not None:
                raise self.error
        except BaseException:
            self.events.append("rollback")
            raise
        else:
            self.events.append("commit")


class MockOperationIdempotency(OperationIdempotency):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: (
            NewOperationReservationDTO
            | CompletedSynchronousOperationDTO
            | AcceptedAsyncOperationDTO
            | RecoveryRequiredOperationDTO
        ) = SAVED_RESULT
        self.completed_result: CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO = (
            replace(SAVED_RESULT, created=True)
        )
        self.error: Exception | None = None
        self.completion_error: Exception | None = None
        self.calls = 0
        self.context: IdempotencyContextDTO | None = None
        self.access: AccessContextDTO | None = None
        self.authorization: object | None = None
        self.fingerprint: RequestFingerprint | None = None
        self.lookup_authority: OperationLookupAuthority | None = None
        self.expected_kind: OperationReplayKind | None = None

    @override
    async def reserve_or_recover[ProjectScope: ProjectId | None](
        self,
        *,
        context: IdempotencyContextDTO,
        access: AccessContextDTO,
        authorization: AuthorizedOperationScope[ProjectScope],
        fingerprint: RequestFingerprint,
        expected_replay_kind: OperationReplayKind,
        lookup_authority: OperationLookupAuthority | None = None,
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
        self.lookup_authority = lookup_authority
        self.expected_kind = expected_replay_kind
        assert expected_replay_kind is OperationReplayKind.SAFE_RESULT
        if self.error is not None:
            raise self.error
        return self.result

    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        self.events.append("complete")
        assert operation == NEW_RESERVATION
        assert replay_kind is OperationReplayKind.SAFE_RESULT
        if self.completion_error is not None:
            raise self.completion_error
        return self.completed_result


class MockMetadataAuthorizer(ProjectMetadataAuthorizer):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.error: Exception | None = None

    @override
    async def require_read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectActionAuthorizationDTO:
        return await self.require_change(access=access, project_id=project_id)

    @override
    async def require_change(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectActionAuthorizationDTO:
        self.events.append("authorize")
        if self.error is not None:
            raise self.error
        return ProjectActionAuthorizationDTO(ORGANIZATION_ID, project_id)


class MockMetadataRepository(ProjectMetadataRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.metadata = ProjectMetadata(
            project_id=PROJECT_ID,
            organization_id=ORGANIZATION_ID,
            name=None,
            display_name=" legacy\nlabel ",
            revision=0,
        )
        self.saved = ProjectMetadataDTO(
            ORGANIZATION_ID, PROJECT_ID, ResourceName("original"), "Original", 1
        )
        self.error: Exception | None = None

    @override
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectMetadata:
        self.events.append("load")
        return self.metadata

    @override
    async def save(
        self,
        metadata: ProjectMetadata,
        *,
        expected_revision: int,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        self.events.append("save")
        if self.error is not None:
            raise self.error

    @override
    async def original(
        self, *, organization_id: OrganizationId, project_id: ProjectId, operation_id: OperationId
    ) -> ProjectMetadataDTO:
        self.events.append("original")
        return self.saved


SCOPE = ResourceNameScopeDTO(InstallationId(UUID(int=4)), ORGANIZATION_ID)


class MockMetadataScope(ProjectMetadataFactsReader):
    @override
    async def scope(self, *, access: AccessContextDTO) -> ResourceNameScopeDTO:
        return SCOPE

    @override
    async def read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectMetadataAuthorizationFactsDTO | None:
        return None

    @override
    async def read_for_change(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectMetadataAuthorizationFactsDTO | None:
        return None


class MockResourceBindings(ResourceNameBindingReader):
    def __init__(self, bindings: tuple[ResourceNameBindingDTO, ...]) -> None:
        self.bindings = bindings

    @override
    async def read(self, query: ResolveResourceNameQuery) -> tuple[ResourceNameBindingDTO, ...]:
        return self.bindings
