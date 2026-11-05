"""Serve real HTTP adapters with synthetic collaborators for SDK conformance.

This factory never opens a database or calls Kratos, Hydra or a model provider.
It is test support, not an alternative deployment or authorization implementation.
"""

import asyncio
import base64
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from enum import StrEnum
from json import JSONDecodeError
from typing import Literal, override
from uuid import UUID

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, HttpUrl, JsonValue
from starlette.datastructures import UploadFile
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response, StreamingResponse

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.commands.create_project_command import (
    CreateProjectCommand,
)
from inframeld_backend.access.application.commands.decide_human_oauth_consent_command import (
    DecideHumanOAuthConsentCommand,
)
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.created_project_dto import CreatedProjectDTO
from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_consent_details_dto import (
    HumanOAuthConsentDetailsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.my_organization_access_dto import (
    MyOrganizationAccessDTO,
)
from inframeld_backend.access.application.dtos.oauth_consent_continuation_dto import (
    OAuthConsentContinuationDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_creation_result_dto import (
    ProjectCreationResultDTO,
)
from inframeld_backend.access.application.dtos.project_member_dto import ProjectMemberDTO
from inframeld_backend.access.application.dtos.project_members_page_facts_dto import (
    ProjectMembersPageFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_change_result_dto import (
    ProjectMetadataChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_dto import ProjectMetadataDTO
from inframeld_backend.access.application.dtos.public_discovery_dto import PublicDiscoveryDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.application.errors.retired_project_name_error import (
    RetiredProjectNameError,
)
from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_admitter import HumanAdmitter
from inframeld_backend.access.application.protocols.human_oauth_consent_handler import (
    HumanOAuthConsentHandler,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)
from inframeld_backend.access.application.protocols.my_organization_access_reader import (
    MyOrganizationAccessReader,
)
from inframeld_backend.access.application.protocols.project_creator import ProjectCreator
from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.application.protocols.project_members_facts_reader import (
    ProjectMembersFactsReader,
)
from inframeld_backend.access.application.protocols.project_membership_change_service_factory import (
    ProjectMembershipChangeServiceFactory,
)
from inframeld_backend.access.application.protocols.project_membership_changer import (
    ProjectMembershipChanger,
)
from inframeld_backend.access.application.protocols.project_metadata_changer import (
    ProjectMetadataChanger,
)
from inframeld_backend.access.application.protocols.project_metadata_reader import (
    ProjectMetadataReader,
)
from inframeld_backend.access.application.protocols.project_name_resolver import ProjectNameResolver
from inframeld_backend.access.application.queries.get_project_metadata_query import (
    GetProjectMetadataQuery,
)
from inframeld_backend.access.application.queries.inspect_human_oauth_consent_query import (
    InspectHumanOAuthConsentQuery,
)
from inframeld_backend.access.application.queries.resolve_project_name_query import (
    ResolveProjectNameQuery,
)
from inframeld_backend.access.application.services.project_members_service import (
    ProjectMembersService,
)
from inframeld_backend.access.application.value_objects.browser_session_credential import (
    BrowserSessionCredential,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.project_creation_policy import ProjectCreationPolicy
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.human_session_dependency import (
    HumanSessionDependency,
)
from inframeld_backend.access.http.routes.current_session_routes import create_session_router
from inframeld_backend.access.http.routes.discovery_routes import create_discovery_router
from inframeld_backend.access.http.routes.human_admission_routes import (
    create_human_admission_router,
)
from inframeld_backend.access.http.routes.human_oauth_consent_routes import (
    create_human_oauth_consent_router,
)
from inframeld_backend.access.http.routes.organization_access_routes import (
    create_organization_access_router,
)
from inframeld_backend.access.http.routes.project_creation_routes import (
    create_project_creation_router,
)
from inframeld_backend.access.http.routes.project_grant_routes import create_project_grant_router
from inframeld_backend.access.http.routes.project_members_routes import (
    create_project_members_router,
)
from inframeld_backend.access.http.routes.project_membership_routes import (
    create_project_membership_router,
)
from inframeld_backend.access.http.routes.project_metadata_routes import (
    create_project_metadata_router,
)
from inframeld_backend.shared.application.dtos.accepted_operation_lookup_dto import (
    AcceptedOperationLookupDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.in_progress_operation_dto import (
    InProgressOperationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.deletion_status_lookup import (
    DeletionStatusLookup,
)
from inframeld_backend.shared.application.protocols.original_operation_lookup import (
    OriginalOperationLookup,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.http.routes.deletion_status_routes import (
    create_deletion_status_router,
)
from inframeld_backend.shared.http.routes.health_routes import router as health_router
from inframeld_backend.shared.http.routes.original_operation_lookup_routes import (
    create_original_operation_lookup_router,
)
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.openapi_schema_fixture import create_schema_fixture_app


class Kind(StrEnum):
    NONE = "none"
    JSON = "json"
    RAW = "raw"
    MALFORMED = "malformed"
    UNEXPECTED = "unexpected"
    REDIRECT = "redirect"
    SLOW = "slow"
    DISCONNECT = "disconnect"


PRINCIPAL = PrincipalId(UUID("00000000-0000-4000-8000-000000000001"))
IDENTITY = VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("alice"))


class SDKFaultRequestDTO(BaseModel):
    """Arrange an isolated wire fault outside the delivered API contract."""

    kind: Kind
    body: JsonValue = None
    status: int = 200
    body_base64: str = Field(default="", alias="bodyBase64")
    content_type: str | None = Field(default="application/json", alias="contentType")
    headers: list[tuple[str, str]] = Field(default_factory=list[tuple[str, str]])


class MockSDKBrowserAuthenticator(HumanSessionAuthenticator):
    @override
    async def authenticate(self, credential: BrowserSessionCredential | None) -> AccessContextDTO:
        if credential is None or credential.value != "sdk-cookie":
            raise AuthenticationRequiredError()

        return AccessContextDTO(PRINCIPAL, MockAuthenticationEvidence.browser(IDENTITY))


class MockSDKTokenAuthenticator(HumanAccessTokenAuthenticator):
    @override
    async def authenticate(self, credential: HumanAccessTokenCredential | None) -> AccessContextDTO:
        if credential is not None and credential.value == "sdk-denied":
            raise AccessDeniedError()
        if credential is not None and credential.value == "sdk-unavailable":
            raise DependencyUnavailableError()
        if credential is None or credential.value != "sdk-human":
            raise AuthenticationRequiredError()

        return AccessContextDTO(PRINCIPAL, MockAuthenticationEvidence.human_oauth(IDENTITY))


class MockSDKConsentHandler(HumanOAuthConsentHandler):
    @override
    async def inspect(
        self, *, credential: BrowserSessionCredential, query: InspectHumanOAuthConsentQuery
    ) -> HumanOAuthConsentDetailsDTO:
        if credential.value != "sdk-cookie":
            raise AuthenticationRequiredError()
        if query.challenge.value != "a+b&/":
            raise ValueError("The SDK changed the challenge query parameter.")

        return HumanOAuthConsentDetailsDTO(
            IDENTITY,
            OAuthClientId("inframeld-cli"),
            HumanAPIAudience("https://api.test"),
            (HumanOAuthScope.API,),
            (HumanAPIAudience("https://api.test"),),
            True,
            3600,
        )

    @override
    async def decide(
        self, *, credential: BrowserSessionCredential, command: DecideHumanOAuthConsentCommand
    ) -> OAuthConsentContinuationDTO:
        if credential.value != "sdk-cookie":
            raise AuthenticationRequiredError()
        if command.challenge.value != "a+b&/":
            raise ValueError("The SDK changed the consent request body.")

        return OAuthConsentContinuationDTO("https://auth.test/continue")


class MockSDKGrantChanger(ProjectGrantChanger):
    @override
    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        command: AssignProjectUseOnlyGrantCommand,
        context: IdempotencyContextDTO,
    ) -> CompletedSynchronousOperationDTO:
        if context.key.value != "sdk-key":
            raise ValueError("The SDK changed the idempotency header.")

        return CompletedSynchronousOperationDTO(
            OperationId("sdk-operation"),
            True,
            OperationReplayKind.SAFE_RESULT,
            datetime(2030, 1, 1, tzinfo=UTC),
        )


@asynccontextmanager
async def _open_grant_change() -> AsyncGenerator[ProjectGrantChanger]:
    yield MockSDKGrantChanger()


class MockSDKMyOrganizationAccess(MyOrganizationAccessReader):
    @override
    async def read(self, *, access: AccessContextDTO) -> MyOrganizationAccessDTO:
        return MyOrganizationAccessDTO(
            OrganizationId(UUID("00000000-0000-4000-8000-000000000002")),
            access.actor_principal_id,
            7,
            (OrganizationActionGrantDTO(ActionId("create-projects"), False),),
        )


class MockSDKProjectCreator(ProjectCreator):
    """Supply an original typed receipt without simulating persistence or authorization."""

    @override
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateProjectCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectCreationResultDTO:
        operation_id = OperationId("sdk-project-creation")
        return ProjectCreationResultDTO(
            CreatedProjectDTO(
                operation_id,
                command.organization_id,
                ProjectId(UUID("00000000-0000-4000-8000-000000000004")),
                access.actor_principal_id,
                command.name,
                command.display_name.value,
                1,
                0,
                tuple(ActionId(action) for action in ProjectCreationPolicy.INITIAL_ACTIONS),
            ),
            CompletedSynchronousOperationDTO(
                operation_id,
                True,
                OperationReplayKind.SAFE_RESULT,
                datetime(2030, 1, 1, tzinfo=UTC),
            ),
        )


@asynccontextmanager
async def _open_my_organization_access() -> AsyncGenerator[MyOrganizationAccessReader]:
    yield MockSDKMyOrganizationAccess()


@asynccontextmanager
async def _open_project_creator() -> AsyncGenerator[ProjectCreator]:
    yield MockSDKProjectCreator()


class MockSDKHumanAdmitter(HumanAdmitter):
    """Supply typed original outcomes without simulating admission or provider state."""

    @override
    async def admit(
        self,
        *,
        access: AccessContextDTO,
        command: AdmitHumanCommand,
        context: IdempotencyContextDTO,
    ) -> HumanAdmissionResultDTO:
        if command.organization_id.value != UUID("00000000-0000-4000-8000-000000000002"):
            raise ResourceNotFoundError()
        if command.expected_access_revision != 7:
            raise StaleRevisionError()
        if context.key.value != "sdk-admit-key":
            raise ValueError("The SDK changed the admission idempotency header.")
        changed = command.identity_id != UUID("00000000-0000-4000-8000-000000000005")
        operation_id = OperationId("sdk-human-admission")
        return HumanAdmissionResultDTO(
            InstallationId(UUID("00000000-0000-4000-8000-000000000001")),
            VerifiedHumanIdentityDTO(IDENTITY.authority, IdentitySubject(str(command.identity_id))),
            command.organization_id,
            access.actor_principal_id,
            PrincipalId(command.identity_id),
            8 if changed else 7,
            changed,
            CompletedSynchronousOperationDTO(
                operation_id,
                True,
                OperationReplayKind.SAFE_RESULT,
                datetime(2030, 1, 1, tzinfo=UTC),
            ),
        )


@asynccontextmanager
async def _open_human_admitter() -> AsyncGenerator[HumanAdmitter]:
    yield MockSDKHumanAdmitter()


class MockSDKMembershipChanger(ProjectMembershipChanger):
    """Supply typed wire outcomes, without simulating SQL, handover or retained history."""

    @override
    async def add_member(
        self,
        *,
        access: AccessContextDTO,
        command: AddProjectMemberCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        return self._outcome(access, command, context, ProjectMembershipChangeKind.ADD)

    @override
    async def remove_member(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectMemberCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        return self._outcome(access, command, context, ProjectMembershipChangeKind.REMOVE)

    @staticmethod
    def _outcome(
        access: AccessContextDTO,
        command: AddProjectMemberCommand | RemoveProjectMemberCommand,
        context: IdempotencyContextDTO,
        kind: ProjectMembershipChangeKind,
    ) -> ProjectMembershipChangeResultDTO:
        if command.project_id.value != UUID("00000000-0000-4000-8000-000000000003"):
            raise ResourceNotFoundError()
        if command.principal_id.value == UUID("00000000-0000-4000-8000-000000000006"):
            raise ConflictError("The departure requires an eligible replacement.")
        if command.principal_id.value not in {
            UUID("00000000-0000-4000-8000-000000000004"),
            UUID("00000000-0000-4000-8000-000000000005"),
        }:
            raise ResourceNotFoundError()
        if command.expected_access_revision != 7:
            raise StaleRevisionError()
        if context.key.value != "sdk-membership-key":
            raise ValueError("The SDK changed the membership idempotency header.")
        changed = command.principal_id.value != UUID("00000000-0000-4000-8000-000000000005")
        return ProjectMembershipChangeResultDTO(
            InstallationId(UUID("00000000-0000-4000-8000-000000000001")),
            OrganizationId(UUID("00000000-0000-4000-8000-000000000002")),
            command.project_id,
            access.actor_principal_id,
            command.principal_id,
            kind,
            8 if changed else 7,
            changed,
            201 if kind is ProjectMembershipChangeKind.ADD and changed else 200,
            CompletedSynchronousOperationDTO(
                OperationId("sdk-project-membership-" + kind),
                True,
                OperationReplayKind.SAFE_RESULT,
                datetime(2030, 1, 1, tzinfo=UTC),
            ),
        )


class MockSDKMembershipChangeServiceFactory(ProjectMembershipChangeServiceFactory):
    @override
    @asynccontextmanager
    async def open(self) -> AsyncGenerator[ProjectMembershipChanger]:
        yield MockSDKMembershipChanger()


class MockSDKProjectMembersFacts(ProjectMembersFactsReader):
    """Supply controlled observations, without a database or supported admission claim."""

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        after: PrincipalId | None,
        limit: int,
    ) -> ProjectMembersPageFactsDTO | None:
        if project_id.value != UUID("00000000-0000-4000-8000-000000000003"):
            return None
        organization = OrganizationId(UUID("00000000-0000-4000-8000-000000000002"))
        members = (
            ProjectMemberDTO(PRINCIPAL, "SDK Human", PrincipalKind.HUMAN),
            ProjectMemberDTO(
                PrincipalId(UUID("00000000-0000-4000-8000-000000000005")),
                "Stored application",
                PrincipalKind.APPLICATION,
            ),
            ProjectMemberDTO(
                PrincipalId(UUID("00000000-0000-4000-8000-000000000006")),
                "Legacy\nmember 🧭",
                PrincipalKind.HUMAN,
            ),
        )
        bounded = tuple(
            member
            for member in members
            if after is None or member.principal_id.value.int > after.value.int
        )[: limit + 1]
        return ProjectMembersPageFactsDTO(
            InstallationId(UUID(int=123)),
            organization,
            project_id,
            12,
            ProjectActionFactsDTO(
                Principal(
                    access.actor_principal_id,
                    organization,
                    PrincipalKind.HUMAN,
                    PrincipalStatus.ACTIVE,
                ),
                False,
                HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(1))
                if isinstance(access.authentication_evidence, HumanOAuthCredentialBindingDTO)
                else None,
                ProjectStatus.ACTIVE,
                True,
                True,
            ),
            bounded,
        )


@asynccontextmanager
async def _open_project_members() -> AsyncGenerator[ProjectMembersService]:
    yield ProjectMembersService(MockSDKProjectMembersFacts())


class MockSDKProjectMetadata(ProjectMetadataReader, ProjectMetadataChanger, ProjectNameResolver):
    """Supply explicit metadata observations without claiming persistence or grant administration."""

    @staticmethod
    def _metadata(
        project_id: ProjectId,
        name: ResourceName | None = None,
        display_name: str | None = None,
        revision: int = 0,
    ) -> ProjectMetadataDTO:
        return ProjectMetadataDTO(
            OrganizationId(UUID("00000000-0000-4000-8000-000000000002")),
            project_id,
            name,
            "legacy\x01\n" + "x" * 150 if display_name is None else display_name,
            revision,
        )

    @override
    async def get(
        self, *, access: AccessContextDTO, query: GetProjectMetadataQuery
    ) -> ProjectMetadataDTO:
        return self._metadata(query.project_id)

    @override
    async def resolve(
        self, *, access: AccessContextDTO, query: ResolveProjectNameQuery
    ) -> ProjectMetadataDTO:
        project_id = ProjectId(UUID("00000000-0000-4000-8000-000000000003"))
        if query.name == ResourceName("former-support"):
            raise RetiredProjectNameError(project_id, ResourceName("support"))
        return self._metadata(project_id, query.name)

    @override
    async def update(
        self,
        *,
        access: AccessContextDTO,
        command: UpdateProjectMetadataCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMetadataChangeResultDTO:
        if command.expected_metadata_revision != 0:
            raise StaleRevisionError()
        return ProjectMetadataChangeResultDTO(
            self._metadata(
                command.project_id,
                command.name,
                None if command.display_name is None else command.display_name.value,
                1,
            ),
            CompletedSynchronousOperationDTO(
                OperationId("sdk-metadata-operation"),
                True,
                OperationReplayKind.SAFE_RESULT,
                datetime(2030, 1, 1, tzinfo=UTC),
            ),
        )


@asynccontextmanager
async def _open_metadata_reader() -> AsyncGenerator[ProjectMetadataReader]:
    yield MockSDKProjectMetadata()


@asynccontextmanager
async def _open_metadata_changer() -> AsyncGenerator[ProjectMetadataChanger]:
    yield MockSDKProjectMetadata()


@asynccontextmanager
async def _open_name_resolver() -> AsyncGenerator[ProjectNameResolver]:
    yield MockSDKProjectMetadata()


class MockSDKOriginalOperationLookup(OriginalOperationLookup):
    """Supply explicit retained outcomes without a database or business dispatch."""

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> (
        CompletedSynchronousOperationDTO
        | AcceptedOperationLookupDTO
        | InProgressOperationDTO
        | RecoveryRequiredOperationDTO
        | UnresolvedOperationDTO
    ):
        query.expected_authority.require_supported_scope(
            project_id=query.project_id, method=query.method, requested_route=query.requested_route
        )
        metadata = query.requested_route == "/v1/projects/{project_id}/metadata"
        original_action = (
            "edit-project-metadata"
            if metadata
            else "create-projects"
            if query.project_id is None
            else "create-access-groups"
        )
        if (
            query.installation_id.value != UUID("00000000-0000-4000-8000-000000000001")
            or query.organization_id.value != UUID("00000000-0000-4000-8000-000000000002")
            or (
                query.project_id is not None
                and query.project_id.value != UUID("00000000-0000-4000-8000-000000000003")
            )
            or query.expected_authority.action_id.value != original_action
            or (
                query.requested_route == "/v1/projects/{project_id}/grants"
                and query.expected_authority.family
                is not OperationLookupAuthorityFamily.PROJECT_GRANT_READ
            )
        ):
            return UnresolvedOperationDTO()

        if metadata and query.method == "PATCH" and query.key.value == "sdk-metadata-key":
            return CompletedSynchronousOperationDTO(
                OperationId("sdk-metadata-operation"),
                False,
                OperationReplayKind.SAFE_RESULT,
                datetime(2030, 1, 1, tzinfo=UTC),
            )
        operation = OperationId("sdk-original-operation")
        match query.key.value:
            case "completed +/&é" | "issued-secret" | "answer-receipt":
                kind: Literal[
                    OperationReplayKind.SAFE_RESULT,
                    OperationReplayKind.ISSUED_SECRET,
                    OperationReplayKind.ANSWER_RECEIPT,
                ] = OperationReplayKind.SAFE_RESULT
                if query.key.value == "issued-secret":
                    kind = OperationReplayKind.ISSUED_SECRET
                elif query.key.value == "answer-receipt":
                    kind = OperationReplayKind.ANSWER_RECEIPT
                return CompletedSynchronousOperationDTO(
                    operation, False, kind, datetime(2030, 1, 1, tzinfo=UTC)
                )
            case "accepted":
                return AcceptedOperationLookupDTO(operation, None)
            case "accepted-job" if (
                query.expected_authority.family is OperationLookupAuthorityFamily.PROJECT_ACTION_USE
                and query.requested_route == "/v1/original-project-operation"
            ):
                return AcceptedOperationLookupDTO(
                    operation, None, JobId(UUID("00000000-0000-4000-8000-000000000008"))
                )
            case "in-progress":
                return InProgressOperationDTO(operation)
            case "recovery-required":
                return RecoveryRequiredOperationDTO(operation)
            case _:
                return UnresolvedOperationDTO()


@asynccontextmanager
async def _open_original_lookup() -> AsyncGenerator[OriginalOperationLookup]:
    yield MockSDKOriginalOperationLookup()


class MockSDKDeletionStatusLookup(DeletionStatusLookup):
    """Supply content-free application outcomes, without pretending to delete resources."""

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: GetDeletionStatusQuery
    ) -> RetainedDeletionStatusDTO | UnresolvedOperationDTO:
        match query.operation_id.value:
            case "settled +/&é":
                return RetainedDeletionStatusDTO(
                    query.operation_id,
                    JobStatus.SUCCEEDED,
                    True,
                    True,
                    True,
                    True,
                    datetime(2030, 1, 1, tzinfo=UTC),
                )
            case "active":
                return RetainedDeletionStatusDTO(
                    query.operation_id, JobStatus.RUNNING, True, True, False, None, None
                )
            case "unknown":
                return RetainedDeletionStatusDTO(
                    query.operation_id, None, None, None, None, None, None
                )
            case "unavailable":
                raise DependencyUnavailableError()
            case _:
                return UnresolvedOperationDTO()


@asynccontextmanager
async def _open_deletion_status() -> AsyncGenerator[DeletionStatusLookup]:
    yield MockSDKDeletionStatusLookup()


async def _fault_response(fault: SDKFaultRequestDTO | None) -> Response | None:
    """Return an explicitly arranged wire response without changing production routes."""
    if fault is None:
        return None

    headers = {"X-Request-ID": "00000000-0000-4000-8000-000000000099"}
    if fault.kind == Kind.RAW:
        response = Response(
            base64.b64decode(fault.body_base64, validate=True),
            status_code=fault.status,
            media_type=fault.content_type,
            headers=headers,
        )
        response.raw_headers.extend(
            (name.encode("ascii"), value.encode("latin1")) for name, value in fault.headers
        )
        return response
    if fault.kind == Kind.JSON:
        return JSONResponse(
            fault.body, status_code=fault.status, headers=headers, media_type=fault.content_type
        )
    if fault.kind == Kind.MALFORMED:
        return Response(b"{", media_type="application/json", headers=headers)
    if fault.kind == Kind.UNEXPECTED:
        return Response(
            b'{"unrecognized":true}',
            status_code=418,
            media_type="application/json",
            headers=headers,
        )
    if fault.kind == Kind.REDIRECT:
        return RedirectResponse("/health", status_code=307)
    if fault.kind == Kind.SLOW:
        await asyncio.sleep(0.25)
    if fault.kind == Kind.DISCONNECT:
        # Observe one request, then lose its response. This is no persistence proof.
        async def interrupted_body() -> AsyncIterator[bytes]:
            yield b"{"
            raise RuntimeError("Synthetic lost response after an observed request.")

        return StreamingResponse(interrupted_body(), media_type="application/json")

    return None


class SDKCaseRequestDTO(BaseModel):
    """Register the exact native calls owned by one conformance case."""

    calls: dict[str, SDKFaultRequestDTO]


class SDKCaseEvidenceDTO(BaseModel):
    """Retain only one case's wire evidence until the caller collects it."""

    observations: dict[str, dict[str, JsonValue]]
    counts: dict[str, int]


def create_sdk_conformance_app(browser_origin: str | None = None) -> FastAPI:
    application = create_schema_fixture_app()
    origins = (HttpUrl("https://account.test"),)
    if browser_origin is not None:
        origins += (HttpUrl(browser_origin),)

    csrf = CSRFProtectionDependency(origins)
    authenticate = HumanSessionDependency(
        MockSDKBrowserAuthenticator(), csrf, access_token_authenticator=MockSDKTokenAuthenticator()
    )
    discovery_snapshot: ContextVar[PublicDiscoveryDTO | None] = ContextVar("discovery_snapshot")

    @application.middleware("http")
    async def discovery_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        resources = {
            b"/.well-known/oauth-protected-resource": "https://api.test",
            b"/.well-known/oauth-protected-resource/api/v1": "https://api.test/api/v1",
            b"/.well-known/oauth-protected-resource/api/": "https://api.test/api/",
            b"/.well-known/oauth-protected-resource/a%20b": "https://api.test/a%20b",
            b"/.well-known/oauth-protected-resource/api%2Fv1": "https://api.test/api%2Fv1",
            b"/.well-known/oauth-protected-resource/a%25b": "https://api.test/a%25b",
            b"/.well-known/oauth-protected-resource/" + b"%C3%A9" * 1500: (
                "https://api.test/" + "é" * 1500
            ),
        }
        resource = resources.get(request.scope["raw_path"])
        token = discovery_snapshot.set(
            PublicDiscoveryDTO(
                resource,
                "https://auth.test/",
                InstallationId(UUID("00000000-0000-4000-8000-000000000001")),
            )
            if resource is not None
            else None
        )
        try:
            return await call_next(request)
        finally:
            discovery_snapshot.reset(token)

    application.include_router(create_discovery_router(discovery_snapshot.get))
    application.include_router(health_router)
    application.include_router(create_session_router(authenticate))
    application.include_router(create_human_admission_router(authenticate, _open_human_admitter))
    application.include_router(create_project_grant_router(authenticate, _open_grant_change))
    application.include_router(
        create_organization_access_router(authenticate, _open_my_organization_access)
    )
    application.include_router(create_project_creation_router(authenticate, _open_project_creator))
    application.include_router(create_project_members_router(authenticate, _open_project_members))
    application.include_router(
        create_project_membership_router(authenticate, MockSDKMembershipChangeServiceFactory())
    )
    application.include_router(
        create_project_metadata_router(
            authenticate,
            _open_metadata_reader,
            _open_metadata_changer,
            _open_name_resolver,
        )
    )
    application.include_router(
        create_original_operation_lookup_router(authenticate, _open_original_lookup)
    )
    application.include_router(create_deletion_status_router(authenticate, _open_deletion_status))
    application.include_router(create_human_oauth_consent_router(MockSDKConsentHandler(), csrf))
    counts: dict[str, int] = {}
    observations: dict[str, dict[str, JsonValue]] = {}
    faults: dict[str, SDKFaultRequestDTO] = {}

    cases: dict[str, set[str]] = {}

    @application.post("/sdk-control/cases/{case_id}", include_in_schema=False)
    async def configure_case(case_id: str, registration: SDKCaseRequestDTO) -> dict[str, str]:
        if case_id in cases or any(key in faults for key in registration.calls):
            raise HTTPException(status_code=409, detail="Case or call already registered")
        if not registration.calls:
            raise HTTPException(status_code=422, detail="A case requires calls")
        cases[case_id] = set(registration.calls)
        faults.update(registration.calls)
        return {"caseId": case_id}

    @application.get("/sdk-control/counts", include_in_schema=False)
    async def request_counts() -> dict[str, int]:
        return {"_total": counts.get("_total", 0)}

    @application.get("/sdk-control/cases/{case_id}", include_in_schema=False)
    async def case_evidence(case_id: str) -> SDKCaseEvidenceDTO:
        if case_id not in cases:
            raise HTTPException(status_code=404, detail="Case not registered")
        keys = cases[case_id]
        return SDKCaseEvidenceDTO(
            observations={key: observations[key] for key in keys if key in observations},
            counts={key: counts.get(key, 0) for key in keys},
        )

    @application.delete("/sdk-control/cases/{case_id}", include_in_schema=False)
    async def delete_case(case_id: str) -> dict[str, str]:
        if case_id not in cases:
            raise HTTPException(status_code=404, detail="Case not registered")
        for key in cases.pop(case_id):
            faults.pop(key, None)
            observations.pop(key, None)
            counts.pop(key, None)
        return {"caseId": case_id}

    @application.middleware("http")
    async def inject_fault(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not request.url.path.startswith("/sdk-control/") and request.method != "OPTIONS":
            # Independent totals still expose a retry that drops the witness header.
            counts["_total"] = counts.get("_total", 0) + 1
        key = request.headers.get("X-SDK-Test")
        if key is not None and key in faults:
            counts[key] = counts.get(key, 0) + 1
            observations[key] = {
                "method": request.method,
                "path": request.scope["raw_path"].split(b"?", 1)[0].decode("ascii"),
                "query": request.url.query,
                "cursor": request.query_params.get("cursor", ""),
                "authorization": request.headers.get("authorization", ""),
                "csrf": request.headers.get("x-inframeld-csrf", ""),
                "origin": request.headers.get("origin", ""),
                "headers": dict(request.headers),
                "rawBodyBase64": base64.b64encode(await request.body()).decode(),
            }
            if request.url.path == "/contract-fixture/upload":
                # Cache the wire body for the downstream route's independent parser.
                await request.body()
                async with request.form() as form:
                    upload = form.get("file")
                    if isinstance(upload, UploadFile):
                        observations[key]["fileBase64"] = base64.b64encode(
                            await upload.read()
                        ).decode()
                        observations[key]["fileName"] = upload.filename or ""
                    label = form.get("label")
                    if isinstance(label, str):
                        observations[key]["label"] = label
            if request.headers.get("content-type", "").split(";")[0] == "application/json":
                try:
                    payload_json: JsonValue = await request.json()
                    observations[key]["jsonBody"] = payload_json
                except JSONDecodeError:
                    pass
            if request.url.path == "/contract-fixture/payload":
                try:
                    payload: object = await request.json()
                except JSONDecodeError:
                    payload = {}
                if isinstance(payload, dict):
                    observations[key] |= {
                        "optionalAbsent": "optional_nullable" not in payload,
                        "optionalNull": "optional_nullable" in payload
                        and payload["optional_nullable"] is None,
                        "requiredNull": "required_nullable" in payload
                        and payload["required_nullable"] is None,
                    }

        arranged = await _fault_response(faults.get(key or ""))
        response = arranged if arranged is not None else await call_next(request)
        if key is not None and key in faults:
            observations[key]["status"] = response.status_code
        return response

    if browser_origin is not None:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=[browser_origin],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            expose_headers=["X-Request-ID", "WWW-Authenticate"],
        )

    return application
