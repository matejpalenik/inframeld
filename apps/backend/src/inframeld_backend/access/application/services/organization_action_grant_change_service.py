import asyncio
from json import dumps
from typing import override

from inframeld_backend.access.application.commands.remove_organization_action_grant_command import (
    RemoveOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_organization_action_grant_command import (
    SetOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.organization_action_grant_change_result_dto import (
    OrganizationActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.protocols.organization_action_grant_changer import (
    OrganizationActionGrantChanger,
)
from inframeld_backend.access.application.protocols.organization_action_grant_result_reader import (
    OrganizationActionGrantResultReader,
)
from inframeld_backend.access.application.protocols.organization_action_grant_writer import (
    OrganizationActionGrantWriter,
)
from inframeld_backend.access.application.protocols.organization_grant_management_facts_reader import (
    OrganizationGrantManagementFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.organization_grant_policy import (
    OrganizationGrantPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
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


class OrganizationActionGrantChangeService(OrganizationActionGrantChanger):
    """Change one Organization grant while retaining its original effect under current authority."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        organization_grant_facts_reader: OrganizationGrantManagementFactsReader,
        organization_grant_writer: OrganizationActionGrantWriter,
        organization_grant_result_reader: OrganizationActionGrantResultReader,
        operation_idempotency: OperationIdempotency,
        request_fingerprint_service: RequestFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._organization_grant_facts_reader = organization_grant_facts_reader
        self._organization_grant_writer = organization_grant_writer
        self._organization_grant_result_reader = organization_grant_result_reader
        self._operation_idempotency = operation_idempotency
        self._request_fingerprint_service = request_fingerprint_service

    @override
    async def set_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetOrganizationActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> OrganizationActionGrantChangeResultDTO:
        return await self._change(access=access, command=command, context=context)

    @override
    async def remove_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveOrganizationActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> OrganizationActionGrantChangeResultDTO:
        return await self._change(access=access, command=command, context=context)

    async def _change(
        self,
        *,
        access: AccessContextDTO,
        command: SetOrganizationActionGrantCommand | RemoveOrganizationActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> OrganizationActionGrantChangeResultDTO:
        """Authorize before history, then check fresh-write state and handover under coordination."""
        setting = isinstance(command, SetOrganizationActionGrantCommand)
        method = HttpMethod.PUT if setting else HttpMethod.DELETE
        route = f"/v1/organizations/{command.organization_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}"
        if context.method != method or context.requested_route != route:
            raise RuntimeError("Organization grant context changed its original method or route.")
        if not OrganizationGrantPolicy.supports_action(command.action_id):
            raise InvalidInputError("This action does not belong to the Organization catalogue.")

        fingerprint = self._request_fingerprint_service.fingerprint(
            purpose="access.organization.action-grant:v1",
            canonical_request=dumps(
                {
                    "organizationId": str(command.organization_id.value),
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
                facts = await self._organization_grant_facts_reader.lock_for_management(
                    access=access,
                    organization_id=command.organization_id,
                    recipient_principal_id=command.recipient_principal_id,
                    action_id=command.action_id,
                )
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.organization_id != command.organization_id
                    or facts.action_id != command.action_id
                    or facts.actor.id != access.actor_principal_id
                    or facts.actor.organization_id != facts.organization_id
                    or type(facts.access_revision) is not int
                    or not 0 <= facts.access_revision <= RevisionValidation.MAX_VALUE
                ):
                    raise RuntimeError("Organization grant facts changed actor, scope or revision.")

                PrincipalAccessEvaluationService.require_human(access=access, principal=facts.actor)
                eligibility = PrincipalAccessEvaluationService.evaluate(
                    access=access,
                    principal=facts.actor,
                    has_pending_recovery=facts.actor_has_pending_recovery,
                    oauth_credential_facts=facts.actor_oauth_credential_facts,
                )
                PrincipalAccessEvaluationService.require_current_credential(
                    access=access, principal_access=eligibility
                )
                if not OrganizationGrantPolicy.may_manage(
                    actor_access=eligibility, can_grant_action=facts.actor_can_grant
                ):
                    raise AccessDeniedError()

                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        family=OperationLookupAuthorityFamily.ORGANIZATION_GRANT_READ,
                        action_id=command.action_id,
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._require_safe_completed_operation(operation)
                    original = await self._organization_grant_result_reader.original(
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
                    if isinstance(command, SetOrganizationActionGrantCommand)
                    else before.remove()
                )
                if before.can_grant is True and after.can_grant is not True:
                    if any(
                        candidate.principal.organization_id != facts.organization_id
                        for candidate in facts.other_grantors
                    ):
                        raise RuntimeError("Organization handover returned a foreign candidate.")
                    candidates = tuple(
                        candidate
                        for candidate in facts.other_grantors
                        if candidate.principal.id != command.recipient_principal_id
                    )
                    if not OrganizationGrantPolicy.has_remaining_grantor(candidates):
                        raise ConflictError("The Organization must retain an eligible grantor.")

                changed = before != after
                if changed and facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Organization Access revision cannot advance.")
                await self._organization_grant_writer.save_change(
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
                    raise ConflictError("Organization grant completion changed its operation.")

                result = OrganizationActionGrantChangeResultDTO(
                    installation_id=facts.installation_id,
                    organization_id=facts.organization_id,
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
                await self._organization_grant_writer.save_result(
                    result=result,
                    before_revision=facts.access_revision,
                    before_can_grant=before.can_grant,
                )
                return result
        except TimeoutError as error:
            raise DependencyUnavailableError() from error

    @staticmethod
    def _require_recipient(
        facts: OrganizationGrantManagementFactsDTO,
        command: SetOrganizationActionGrantCommand | RemoveOrganizationActionGrantCommand,
    ) -> None:
        """Check fresh target scope, applying account eligibility only to new assignments."""
        recipient = facts.recipient
        if recipient is None:
            raise ResourceNotFoundError()
        if (
            recipient.id != command.recipient_principal_id
            or recipient.organization_id != facts.organization_id
        ):
            raise RuntimeError("Organization grant facts changed the recipient scope.")
        if recipient.kind is not PrincipalKind.HUMAN:
            raise InvalidInputError("Only admitted humans may hold Organization grants.")
        if isinstance(command, SetOrganizationActionGrantCommand) and not (
            OrganizationGrantPolicy.may_receive(
                recipient_access=PrincipalAccessPolicyInput(
                    principal=recipient,
                    has_pending_recovery=facts.recipient_has_pending_recovery,
                    credential_is_current=True,
                ),
                has_coherent_identity=facts.recipient_has_coherent_identity,
            )
        ):
            raise ConflictError("The recipient is not currently eligible for assignment.")

    @staticmethod
    def _require_safe_completed_operation(operation: object) -> CompletedSynchronousOperationDTO:
        """Require a safe synchronous completion before using its retained business receipt."""
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The Organization grant has no safe original result.")
        return operation

    @staticmethod
    def _require_matching_original(
        facts: OrganizationGrantManagementFactsDTO,
        command: SetOrganizationActionGrantCommand | RemoveOrganizationActionGrantCommand,
        completed: CompletedSynchronousOperationDTO,
        original: OrganizationActionGrantChangeResultDTO,
    ) -> None:
        """Reject altered scope or outcome rather than redispatching uncertain original work."""
        setting = isinstance(command, SetOrganizationActionGrantCommand)
        if (
            original.operation != completed
            or original.installation_id != facts.installation_id
            or original.organization_id != facts.organization_id
            or original.actor_principal_id != facts.actor.id
            or original.recipient_principal_id != command.recipient_principal_id
            or original.action_id != command.action_id
            or original.method != (HttpMethod.PUT if setting else HttpMethod.DELETE)
            or original.can_grant != (command.can_grant if setting else None)
            or original.access_revision != command.expected_access_revision + int(original.changed)
            or not 0 <= original.access_revision <= RevisionValidation.MAX_VALUE
            or original.status_code not in ({200, 201} if setting else {200})
            or (original.status_code == 201 and not original.changed)
        ):
            raise ConflictError("The original Organization grant result is incoherent.")
