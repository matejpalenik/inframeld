import asyncio
from dataclasses import replace
from json import dumps
from typing import override

from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grant_facts_dto import (
    ModelConnectionGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_result_dto import (
    ModelConnectionGrantResultDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.protocols.model_connection_grant_changer import (
    ModelConnectionGrantChanger,
)
from inframeld_backend.access.application.protocols.model_connection_grant_repository import (
    ModelConnectionGrantRepository,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
from inframeld_backend.access.domain.policies.model_connection_grant_policy import (
    ModelConnectionGrantPolicy,
)
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
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
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


class ModelConnectionGrantChangeService(ModelConnectionGrantChanger):
    def __init__(
        self,
        transactions: TransactionManager,
        repository: ModelConnectionGrantRepository,
        idempotency: OperationIdempotency,
        fingerprints: RequestFingerprintService,
    ) -> None:
        self._transactions = transactions
        self._repository = repository
        self._idempotency = idempotency
        self._fingerprints = fingerprints

    @override
    async def change(
        self,
        access: AccessContextDTO,
        command: ChangeModelConnectionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> ModelConnectionGrantResultDTO:
        method = HttpMethod.DELETE if command.can_grant is None else HttpMethod.PUT
        route = f"/v1/model-connections/{command.model_connection_id.value}/grants/{command.recipient_id.value}/{command.action.value}"
        if context.method != method or context.requested_route != route:
            raise RuntimeError("Model connection grant changed the exact operation route.")
        fingerprint = self._fingerprints.fingerprint(
            purpose="access.model-connection.action-grant:v1",
            canonical_request=dumps(
                [route, method.value, command.can_grant, command.expected_access_revision],
                separators=(",", ":"),
            ).encode(),
        )
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                facts = await self._repository.lock_for_change(access, command)
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.model_connection_id != command.model_connection_id
                    or facts.action is not command.action
                    or facts.actor.principal.id != access.actor_principal_id
                    or facts.actor.principal.organization_id != facts.organization_id
                ):
                    raise RuntimeError("Model connection grant changed its exact target or actor.")
                self.require_authority(access, facts)
                target = ModelConnectionGrantTargetDTO(facts.project_id, facts.model_connection_id)
                operation = await self._idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.MODEL_CONNECTION_GRANT_READ,
                        ActionId(command.action.value),
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._safe_completion(operation)
                    original = await self._repository.original(facts, completed)
                    if (
                        original.operation != completed
                        or original.target != target
                        or original.recipient_id != command.recipient_id
                        or original.action is not command.action
                        or original.can_grant is not command.can_grant
                        or original.access_revision
                        != command.expected_access_revision + int(original.changed)
                        or (
                            original.status_code == 201
                            and (command.can_grant is None or not original.changed)
                        )
                    ):
                        raise ConflictError(
                            "The original model connection grant result is incoherent."
                        )
                    return original

                RevisionValidation.require(facts.access_revision)
                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                self._require_recipient(facts, command)
                before = facts.assignment
                after = (
                    before.remove()
                    if command.can_grant is None
                    else before.set_level(can_grant=command.can_grant)
                )
                self._require_handover(facts, command.recipient_id, after)
                changed = before != after
                if changed and facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project access revision is exhausted.")
                if changed:
                    await self._repository.save_change(
                        facts, command.recipient_id, after, operation.operation_id
                    )
                completed = self._safe_completion(
                    await self._idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise ConflictError("Model connection grant completion changed its operation.")
                result = ModelConnectionGrantResultDTO(
                    target,
                    command.recipient_id,
                    command.action,
                    after.can_grant,
                    facts.access_revision + int(changed),
                    changed,
                    201 if command.can_grant is not None and before.can_grant is None else 200,
                    completed,
                )
                await self._repository.save_result(facts, result)
                return result
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def require_authority(access: AccessContextDTO, facts: ModelConnectionGrantFactsDTO) -> None:
        actor = facts.actor
        PrincipalAccessEvaluationService.require_human(access=access, principal=actor.principal)
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=actor.principal,
            has_pending_recovery=actor.has_pending_recovery,
            oauth_credential_facts=actor.oauth_credential_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=actor.principal.status,
            project_status=actor.project_status,
            is_project_member=actor.is_project_member,
        ):
            raise ResourceNotFoundError()
        if not ProjectGrantDelegationPolicy.may_delegate_project_action(
            actor_access=eligibility,
            actor_is_project_member=actor.is_project_member,
            actor_can_grant_action=facts.actor_can_grant,
        ):
            raise AccessDeniedError()

    @staticmethod
    def _require_recipient(
        facts: ModelConnectionGrantFactsDTO, command: ChangeModelConnectionGrantCommand
    ) -> None:
        recipient = facts.recipient
        if recipient is None:
            raise ResourceNotFoundError()
        if (
            recipient.id != command.recipient_id
            or recipient.organization_id != facts.organization_id
        ):
            raise RuntimeError("Model connection grant changed the exact recipient.")
        if command.can_grant is None:
            return
        if not facts.recipient_is_project_member:
            raise ResourceNotFoundError()
        if not ModelConnectionGrantPolicy.supports_recipient(command.action, recipient.kind) or (
            recipient.kind is PrincipalKind.APPLICATION and command.can_grant
        ):
            raise InvalidInputError(
                "This model connection action or level does not support the recipient."
            )
        if not ModelConnectionGrantPolicy.may_assign(
            recipient_access=PrincipalAccessPolicyInput(
                recipient, facts.recipient_has_pending_recovery, True
            ),
            is_project_member=facts.recipient_is_project_member,
            has_coherent_identity=facts.recipient_has_coherent_identity,
            application_is_project_bound=facts.application_is_project_bound,
            can_grant=command.can_grant,
        ):
            raise ConflictError("The recipient is not currently eligible for assignment.")

    @staticmethod
    def _require_handover(
        facts: ModelConnectionGrantFactsDTO, recipient_id: PrincipalId, after: ActionGrantState
    ) -> None:
        if facts.assignment.can_grant is not True or after.can_grant is True:
            return
        if any(
            candidate.principal.organization_id != facts.organization_id
            for candidate in facts.grantors
        ):
            raise RuntimeError("Model connection handover changed the Organization.")
        if not ProjectDeparturePolicy.may_depart(
            (
                ProjectDepartureResponsibilityPolicyInput(
                    target_kind=ProjectDepartureTargetKind.MODEL_CONNECTION,
                    action_id=ActionId(facts.action.value),
                    candidates=tuple(
                        replace(candidate, can_grant=False)
                        if candidate.principal.id == recipient_id
                        else candidate
                        for candidate in facts.grantors
                    ),
                ),
            )
        ):
            raise ConflictError("The target must retain an eligible human grantor.")

    @staticmethod
    def _safe_completion(operation: object) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The model connection grant has no safe completed result.")
        return operation
