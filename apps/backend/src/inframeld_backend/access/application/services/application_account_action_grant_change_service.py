import asyncio
from dataclasses import replace
from json import dumps
from typing import override

from inframeld_backend.access.application.commands.remove_application_account_action_grant_command import (
    RemoveApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_action_grant_change_result_dto import (
    ApplicationAccountActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.access.application.protocols.application_account_action_grant_changer import (
    ApplicationAccountActionGrantChanger,
)
from inframeld_backend.access.application.protocols.application_account_action_grant_result_reader import (
    ApplicationAccountActionGrantResultReader,
)
from inframeld_backend.access.application.protocols.application_account_action_grant_writer import (
    ApplicationAccountActionGrantWriter,
)
from inframeld_backend.access.application.protocols.application_account_grant_management_facts_reader import (
    ApplicationAccountGrantManagementFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
from inframeld_backend.access.domain.policies.application_account_grant_policy import (
    ApplicationAccountGrantPolicy,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_departure_policy import ProjectDeparturePolicy
from inframeld_backend.access.domain.policies.project_grant_delegation_policy import (
    ProjectGrantDelegationPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_responsibility_policy_input import (
    ProjectDepartureResponsibilityPolicyInput,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
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
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationAccountActionGrantChangeService(ApplicationAccountActionGrantChanger):
    """Change one ApplicationAccount grant while retaining its original effect under current authority."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        application_account_grant_facts_reader: ApplicationAccountGrantManagementFactsReader,
        application_account_grant_writer: ApplicationAccountActionGrantWriter,
        application_account_grant_result_reader: ApplicationAccountActionGrantResultReader,
        operation_idempotency: OperationIdempotency,
        request_fingerprint_service: RequestFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._application_account_grant_facts_reader = application_account_grant_facts_reader
        self._application_account_grant_writer = application_account_grant_writer
        self._application_account_grant_result_reader = application_account_grant_result_reader
        self._operation_idempotency = operation_idempotency
        self._request_fingerprint_service = request_fingerprint_service

    @override
    async def set_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        return await self._change(access=access, command=command, context=context)

    @override
    async def remove_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        return await self._change(access=access, command=command, context=context)

    async def _change(
        self,
        *,
        access: AccessContextDTO,
        command: SetApplicationAccountActionGrantCommand
        | RemoveApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        """Authorize before history, then check fresh-write state and handover under coordination."""
        setting = isinstance(command, SetApplicationAccountActionGrantCommand)
        method = HttpMethod.PUT if setting else HttpMethod.DELETE
        route = f"/v1/projects/{command.project_id.value}/application-accounts/{command.application_principal_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}"
        if context.method != method or context.requested_route != route:
            raise RuntimeError(
                "ApplicationAccount grant context changed its original method or route."
            )
        if not ApplicationAccountGrantPolicy.supports_recipient(
            action_id=command.action_id, kind=PrincipalKind.HUMAN
        ):
            raise InvalidInputError(
                "This action does not belong to the ApplicationAccount catalogue."
            )

        fingerprint = self._request_fingerprint_service.fingerprint(
            purpose="access.application-accounts.action-grant:v1",
            canonical_request=dumps(
                {
                    "projectId": str(command.project_id.value),
                    "applicationPrincipalId": str(command.application_principal_id.value),
                    "recipientPrincipalId": str(command.recipient_principal_id.value),
                    "actionId": command.action_id.value,
                    "method": method.value,
                    "canGrant": command.can_grant if setting else None,
                    "expectedAccessRevision": command.expected_access_revision,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
        )

        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._application_account_grant_facts_reader.lock_for_management(
                    access=access,
                    project_id=command.project_id,
                    application_principal_id=command.application_principal_id,
                    recipient_principal_id=command.recipient_principal_id,
                    action_id=command.action_id,
                )
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.project_id != command.project_id
                    or facts.application_principal_id != command.application_principal_id
                    or facts.action_id != command.action_id
                    or facts.actor.principal.id != access.actor_principal_id
                    or facts.actor.principal.organization_id != facts.organization_id
                    or type(facts.access_revision) is not int
                    or not 0 <= facts.access_revision <= RevisionValidation.MAX_VALUE
                ):
                    raise RuntimeError(
                        "ApplicationAccount grant facts changed actor, scope or revision."
                    )

                PrincipalAccessEvaluationService.require_human(
                    access=access, principal=facts.actor.principal
                )
                eligibility = PrincipalAccessEvaluationService.evaluate(
                    access=access,
                    principal=facts.actor.principal,
                    has_pending_recovery=facts.actor.has_pending_recovery,
                    oauth_credential_facts=facts.actor.oauth_credential_facts,
                )
                PrincipalAccessEvaluationService.require_current_credential(
                    access=access, principal_access=eligibility
                )
                if (
                    facts.actor.principal.kind is not PrincipalKind.HUMAN
                    or not PrincipalAccessPolicy.may_use_product(eligibility)
                ):
                    raise AccessDeniedError()
                if not ProjectVisibilityPolicy.may_view_project(
                    principal_status=facts.actor.principal.status,
                    project_status=facts.actor.project_status,
                    is_project_member=facts.actor.is_project_member,
                ):
                    raise ResourceNotFoundError()
                if not ProjectGrantDelegationPolicy.may_delegate_project_action(
                    actor_access=eligibility,
                    actor_is_project_member=facts.actor.is_project_member,
                    actor_can_grant_action=facts.actor_can_grant,
                ):
                    raise AccessDeniedError()

                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        family=OperationLookupAuthorityFamily.APPLICATION_ACCOUNT_GRANT_READ,
                        action_id=command.action_id,
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._require_safe_completed_operation(operation)
                    original = await self._application_account_grant_result_reader.original(
                        facts=facts, command=command, context=context, operation=completed
                    )
                    self._require_matching_original(facts, command, completed, original)
                    return original

                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                self._require_recipient(facts, command)
                before = facts.assignment
                after = (
                    before.set_level(can_grant=command.can_grant)
                    if isinstance(command, SetApplicationAccountActionGrantCommand)
                    else before.remove()
                )
                if before.can_grant is True and after.can_grant is not True:
                    if any(
                        candidate.principal.organization_id != facts.organization_id
                        for candidate in facts.grantors
                    ):
                        raise RuntimeError("Target handover returned a foreign candidate.")
                    # Removing direct delegation does not remove this human's unchanged management.
                    candidates = tuple(
                        replace(candidate, can_grant=False)
                        if candidate.principal.id == command.recipient_principal_id
                        else candidate
                        for candidate in facts.grantors
                    )
                    if not ProjectDeparturePolicy.may_depart(
                        (
                            ProjectDepartureResponsibilityPolicyInput(
                                target_kind=ProjectDepartureTargetKind.APPLICATION_ACCOUNT,
                                action_id=command.action_id,
                                candidates=candidates,
                            ),
                        )
                    ):
                        raise ConflictError("The target must retain an eligible human grantor.")

                changed = before != after
                if changed and facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The ApplicationAccount Access revision cannot advance.")
                await self._application_account_grant_writer.save_change(
                    facts=facts,
                    recipient_principal_id=command.recipient_principal_id,
                    after=after,
                    operation_id=operation.operation_id,
                )
                completed = self._require_safe_completed_operation(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise ConflictError(
                        "ApplicationAccount grant completion changed its operation."
                    )

                result = ApplicationAccountActionGrantChangeResultDTO(
                    installation_id=facts.installation_id,
                    organization_id=facts.organization_id,
                    project_id=facts.project_id,
                    application_principal_id=facts.application_principal_id,
                    actor_principal_id=access.actor_principal_id,
                    recipient_principal_id=command.recipient_principal_id,
                    action_id=command.action_id,
                    method=method,
                    can_grant=after.can_grant,
                    access_revision=facts.access_revision + int(changed),
                    changed=changed,
                    status_code=201 if setting and before.can_grant is None else 200,
                    operation=completed,
                )
                await self._application_account_grant_writer.save_result(
                    result=result,
                    before_revision=facts.access_revision,
                    before_can_grant=before.can_grant,
                )
                return result
        except TimeoutError as error:
            raise DependencyUnavailableError() from error

    @staticmethod
    def _require_recipient(
        facts: ApplicationAccountGrantManagementFactsDTO,
        command: SetApplicationAccountActionGrantCommand
        | RemoveApplicationAccountActionGrantCommand,
    ) -> None:
        """Check fresh target scope, applying account eligibility only to new assignments."""
        recipient = facts.recipient
        if recipient is None:
            raise ResourceNotFoundError()
        if (
            recipient.id != command.recipient_principal_id
            or recipient.organization_id != facts.organization_id
        ):
            raise RuntimeError("ApplicationAccount grant facts changed the recipient scope.")
        if (
            isinstance(command, SetApplicationAccountActionGrantCommand)
            and not facts.recipient_is_project_member
        ):
            raise ResourceNotFoundError()
        if not ApplicationAccountGrantPolicy.supports_recipient(
            action_id=command.action_id, kind=recipient.kind
        ):
            raise InvalidInputError(
                "This action and grant level do not support the recipient kind."
            )
        if isinstance(
            command, SetApplicationAccountActionGrantCommand
        ) and not ApplicationAccountGrantPolicy.may_receive(
            recipient_access=PrincipalAccessPolicyInput(
                principal=recipient,
                has_pending_recovery=facts.recipient_has_pending_recovery,
                credential_is_current=True,
            ),
            is_project_member=facts.recipient_is_project_member,
            has_coherent_identity=facts.recipient_has_coherent_identity,
        ):
            raise ConflictError("The recipient is not currently eligible for assignment.")

    @staticmethod
    def _require_safe_completed_operation(operation: object) -> CompletedSynchronousOperationDTO:
        """Require a safe synchronous completion before using its retained business receipt."""
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The ApplicationAccount grant has no safe original result.")
        return operation

    @staticmethod
    def _require_matching_original(
        facts: ApplicationAccountGrantManagementFactsDTO,
        command: SetApplicationAccountActionGrantCommand
        | RemoveApplicationAccountActionGrantCommand,
        completed: CompletedSynchronousOperationDTO,
        original: ApplicationAccountActionGrantChangeResultDTO,
    ) -> None:
        """Reject altered scope or outcome rather than redispatching uncertain original work."""
        setting = isinstance(command, SetApplicationAccountActionGrantCommand)
        if (
            original.operation != completed
            or original.installation_id != facts.installation_id
            or original.organization_id != facts.organization_id
            or original.project_id != facts.project_id
            or original.application_principal_id != facts.application_principal_id
            or original.actor_principal_id != facts.actor.principal.id
            or original.recipient_principal_id != command.recipient_principal_id
            or original.action_id != command.action_id
            or original.method != (HttpMethod.PUT if setting else HttpMethod.DELETE)
            or original.can_grant != (command.can_grant if setting else None)
            or original.access_revision != command.expected_access_revision + int(original.changed)
            or not 0 <= original.access_revision <= RevisionValidation.MAX_VALUE
            or original.status_code not in ({200, 201} if setting else {200})
            or (original.status_code == 201 and not original.changed)
        ):
            raise ConflictError("The original ApplicationAccount grant result is incoherent.")
