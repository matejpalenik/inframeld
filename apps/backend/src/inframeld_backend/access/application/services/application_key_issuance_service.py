import asyncio
from typing import override

from inframeld_backend.access.application.commands.issue_application_key_command import (
    IssueApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_creation_dto import (
    ApplicationKeyCreationDTO,
)
from inframeld_backend.access.application.dtos.application_key_issuance_facts_dto import (
    ApplicationKeyIssuanceFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_issuance_record_dto import (
    ApplicationKeyIssuanceRecordDTO,
)
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.application.protocols.application_key_issuance_facts_reader import (
    ApplicationKeyIssuanceFactsReader,
)
from inframeld_backend.access.application.protocols.application_key_issuance_writer import (
    ApplicationKeyIssuanceWriter,
)
from inframeld_backend.access.application.protocols.application_key_issuer import (
    ApplicationKeyIssuer,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.application_key_issuance_fingerprint_service import (
    ApplicationKeyIssuanceFingerprintService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.application_key_issuance_policy import (
    ApplicationKeyIssuancePolicy,
)
from inframeld_backend.access.domain.policies.application_key_lifetime_policy import (
    ApplicationKeyLifetimePolicy,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationKeyIssuanceService(ApplicationKeyIssuer):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        issuance_facts_reader: ApplicationKeyIssuanceFactsReader,
        issuance_writer: ApplicationKeyIssuanceWriter,
        operation_idempotency: OperationIdempotency,
        issuance_fingerprint_service: ApplicationKeyIssuanceFingerprintService,
        http_profile: ApplicationKeyVerificationProfileDTO | None,
        mcp_profile: ApplicationKeyVerificationProfileDTO | None,
        default_lifetime_seconds: int,
        maximum_lifetime_seconds: int,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._issuance_facts_reader = issuance_facts_reader
        self._issuance_writer = issuance_writer
        self._operation_idempotency = operation_idempotency
        self._issuance_fingerprint_service = issuance_fingerprint_service
        self._http_profile = http_profile
        self._mcp_profile = mcp_profile
        self._default_lifetime_seconds = default_lifetime_seconds
        self._maximum_lifetime_seconds = maximum_lifetime_seconds

    @override
    async def issue(
        self,
        *,
        access: AccessContextDTO,
        command: IssueApplicationKeyCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationKeyIssueResultDTO:
        route = f"/v1/projects/{command.project_id.value}/application-accounts/{command.application_principal_id.value}/keys"
        if context.method != HttpMethod.POST or context.requested_route != route:
            raise RuntimeError("Application-key issuance changed its original method or route.")
        fingerprint = self._issuance_fingerprint_service.for_issue(command)
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._issuance_facts_reader.lock_for_issue(
                    access=access,
                    project_id=command.project_id,
                    application_principal_id=command.application_principal_id,
                )
                if facts is None:
                    raise ResourceNotFoundError()
                self._authorize(access, command, facts)
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.ISSUED_SECRET,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._completion(operation, created=False)
                    original = await self._issuance_facts_reader.read_original(
                        organization_id=facts.organization_id,
                        project_id=command.project_id,
                        application_principal_id=command.application_principal_id,
                        issuer_principal_id=access.actor_principal_id,
                        operation_id=completed.operation_id,
                    )
                    if original is None:
                        raise DependencyUnavailableError()
                    if (
                        original.operation_id != completed.operation_id
                        or original.organization_id != facts.organization_id
                        or original.installation_id != facts.installation_id
                        or original.issuer_principal_id != access.actor_principal_id
                        or original.metadata.project_id != command.project_id
                        or original.metadata.application_principal_id
                        != command.application_principal_id
                        or original.metadata.allowed_adapters != command.allowed_adapters
                        or original.access_revision != command.expected_access_revision + 1
                        or original.metadata.revoked_at is not None
                        or original.metadata.expires_at <= original.metadata.created_at
                    ):
                        raise ConflictError("The original application-key result is incoherent.")
                    return ApplicationKeyIssueResultDTO(original, completed, credential=None)

                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                if facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project access revision is exhausted.")
                if type(facts.usable_key_count) is not int or facts.usable_key_count < 0:
                    raise RuntimeError("Application-key count is incoherent.")
                if facts.usable_key_count >= 2:
                    raise ConflictError("The application already has two usable keys.")

                http = (
                    self._http_profile
                    if ApplicationKeyAdapter.HTTP in command.allowed_adapters
                    else None
                )
                mcp = (
                    self._mcp_profile
                    if ApplicationKeyAdapter.MCP in command.allowed_adapters
                    else None
                )
                for adapter, profile in (
                    (ApplicationKeyAdapter.HTTP, http),
                    (ApplicationKeyAdapter.MCP, mcp),
                ):
                    if adapter in command.allowed_adapters:
                        if profile is None:
                            raise DependencyUnavailableError()
                        if profile.adapter is not adapter:
                            raise RuntimeError(
                                "Application-key profile changed its trusted adapter."
                            )
                seconds = (
                    command.expires_in_seconds
                    if command.expires_in_seconds is not None
                    else self._default_lifetime_seconds
                )
                try:
                    expiry = ApplicationKeyLifetimePolicy.expires_at(
                        issued_at=facts.checked_at,
                        lifetime_seconds=seconds,
                        maximum_lifetime_seconds=self._maximum_lifetime_seconds,
                    )
                except ValueError:
                    raise InvalidInputError("The application-key lifetime is invalid.") from None
                credential = ApplicationKeyCredential.generate()
                metadata = ApplicationKeyMetadataDTO(
                    key_id=credential.key_id,
                    application_principal_id=command.application_principal_id,
                    project_id=command.project_id,
                    allowed_adapters=command.allowed_adapters,
                    created_at=facts.checked_at,
                    expires_at=expiry,
                    revoked_at=None,
                )
                original = ApplicationKeyIssuanceRecordDTO(
                    operation_id=operation.operation_id,
                    organization_id=facts.organization_id,
                    installation_id=facts.installation_id,
                    issuer_principal_id=access.actor_principal_id,
                    access_revision=facts.access_revision + 1,
                    metadata=metadata,
                )
                await self._issuance_writer.create(
                    key=ApplicationKeyCreationDTO(
                        original=original,
                        verifier=credential.digest(),
                        http_audience=http.audience if http is not None else None,
                        mcp_audience=mcp.audience if mcp is not None else None,
                    ),
                    expected_project_revision=facts.access_revision,
                )
                completed = self._completion(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.ISSUED_SECRET
                    ),
                    created=True,
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Application-key completion changed its original operation.")
                return ApplicationKeyIssueResultDTO(original, completed, credential)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _authorize(
        access: AccessContextDTO,
        command: IssueApplicationKeyCommand,
        facts: ApplicationKeyIssuanceFactsDTO,
    ) -> None:
        if (
            facts.project_id != command.project_id
            or facts.actor.principal.id != access.actor_principal_id
            or facts.organization_id != facts.actor.principal.organization_id
            or facts.application_principal.id != command.application_principal_id
            or facts.application_principal.organization_id != facts.organization_id
            or facts.application_principal.kind is not PrincipalKind.APPLICATION
        ):
            raise RuntimeError("Application-key facts changed the actor or account scope.")
        RevisionValidation.require(facts.access_revision)
        PrincipalAccessEvaluationService.require_human(
            access=access, principal=facts.actor.principal
        )
        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.actor
        )
        if not ApplicationKeyIssuancePolicy.may_issue_for_account(
            application_principal=facts.application_principal,
            is_project_member=facts.is_application_project_member,
            has_all_action_delegation=facts.has_all_action_delegation,
            manages_all_groups=facts.manages_all_groups,
        ):
            raise AccessDeniedError()

    @staticmethod
    def _completion(value: object, *, created: bool) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(value, CompletedSynchronousOperationDTO)
            or value.replay_kind is not OperationReplayKind.ISSUED_SECRET
            or value.created is not created
        ):
            raise ConflictError("Application-key issuance has no coherent completed result.")
        return value
