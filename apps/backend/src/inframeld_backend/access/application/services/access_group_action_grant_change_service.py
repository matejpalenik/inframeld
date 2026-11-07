import asyncio
from dataclasses import replace
from json import dumps
from typing import override

from inframeld_backend.access.application.commands.remove_access_group_action_grant_command import (
    RemoveAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_access_group_action_grant_command import (
    SetAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_action_grant_change_result_dto import (
    AccessGroupActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_management_facts_dto import (
    AccessGroupGrantManagementFactsDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.access_group_action_grant_changer import (
    AccessGroupActionGrantChanger,
)
from inframeld_backend.access.application.protocols.access_group_action_grant_result_reader import (
    AccessGroupActionGrantResultReader,
)
from inframeld_backend.access.application.protocols.access_group_action_grant_writer import (
    AccessGroupActionGrantWriter,
)
from inframeld_backend.access.application.protocols.access_group_grant_management_facts_reader import (
    AccessGroupGrantManagementFactsReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
from inframeld_backend.access.domain.policies.access_group_grant_policy import (
    AccessGroupGrantPolicy,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_departure_policy import ProjectDeparturePolicy
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


class AccessGroupActionGrantChangeService(AccessGroupActionGrantChanger):
    """Change one AccessGroup grant while retaining its original effect under current authority."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        access_group_grant_facts_reader: AccessGroupGrantManagementFactsReader,
        access_group_grant_writer: AccessGroupActionGrantWriter,
        access_group_grant_result_reader: AccessGroupActionGrantResultReader,
        operation_idempotency: OperationIdempotency,
        request_fingerprint_service: RequestFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._access_group_grant_facts_reader = access_group_grant_facts_reader
        self._access_group_grant_writer = access_group_grant_writer
        self._access_group_grant_result_reader = access_group_grant_result_reader
        self._operation_idempotency = operation_idempotency
        self._request_fingerprint_service = request_fingerprint_service

    @override
    async def set_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetAccessGroupActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupActionGrantChangeResultDTO:
        return await self._change(access=access, command=command, context=context)

    @override
    async def remove_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveAccessGroupActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupActionGrantChangeResultDTO:
        return await self._change(access=access, command=command, context=context)

    async def _change(
        self,
        *,
        access: AccessContextDTO,
        command: SetAccessGroupActionGrantCommand | RemoveAccessGroupActionGrantCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupActionGrantChangeResultDTO:
        """Authorize before history, then check fresh-write state and handover under coordination."""
        setting = isinstance(command, SetAccessGroupActionGrantCommand)
        method = HttpMethod.PUT if setting else HttpMethod.DELETE
        route = f"/v1/projects/{command.project_id.value}/access-groups/{command.group_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}"
        if context.method != method or context.requested_route != route:
            raise RuntimeError("AccessGroup grant context changed its original method or route.")
        if not AccessGroupGrantPolicy.supports_recipient(
            action_id=command.action_id, kind=PrincipalKind.HUMAN, can_grant=True
        ):
            raise InvalidInputError("This action does not belong to the AccessGroup catalogue.")

        fingerprint = self._request_fingerprint_service.fingerprint(
            purpose="access.access-groups.action-grant:v1",
            canonical_request=dumps(
                {
                    "projectId": str(command.project_id.value),
                    "accessGroupId": str(command.group_id.value),
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
                facts = await self._access_group_grant_facts_reader.lock_for_management(
                    access=access,
                    project_id=command.project_id,
                    group_id=command.group_id,
                    recipient_principal_id=command.recipient_principal_id,
                    action_id=command.action_id,
                )
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.project_id != command.project_id
                    or facts.group_id != command.group_id
                    or facts.action_id != command.action_id
                    or facts.actor.principal.id != access.actor_principal_id
                    or facts.actor.principal.organization_id != facts.organization_id
                    or type(facts.access_revision) is not int
                    or not 0 <= facts.access_revision <= RevisionValidation.MAX_VALUE
                ):
                    raise RuntimeError("AccessGroup grant facts changed actor, scope or revision.")

                PrincipalAccessEvaluationService.require_human(
                    access=access, principal=facts.actor.principal
                )
                eligibility = PrincipalAccessEvaluationService.evaluate(
                    access=access,
                    principal=facts.actor.principal,
                    has_pending_recovery=facts.actor.has_pending_recovery,
                    oauth_credential_facts=facts.actor.oauth_credential_facts,
                )
                if not eligibility.credential_is_current:
                    raise HumanOAuthCredentialRejectedError()
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
                if not AccessGroupGrantPolicy.may_manage(
                    actor_access=eligibility,
                    is_project_member=facts.actor.is_project_member,
                    can_grant_action=facts.actor_can_grant,
                    is_group_member=facts.actor_is_group_member,
                    is_group_manager=facts.actor_is_group_manager,
                ):
                    raise AccessDeniedError()

                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        family=OperationLookupAuthorityFamily.ACCESS_GROUP_GRANT_READ,
                        action_id=command.action_id,
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._require_safe_completed_operation(operation)
                    original = await self._access_group_grant_result_reader.original(
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
                    if isinstance(command, SetAccessGroupActionGrantCommand)
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
                                target_kind=ProjectDepartureTargetKind.ACCESS_GROUP,
                                action_id=command.action_id,
                                candidates=candidates,
                            ),
                        )
                    ):
                        raise ConflictError("The target must retain an eligible human grantor.")

                changed = before != after
                if changed and facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The AccessGroup Access revision cannot advance.")
                await self._access_group_grant_writer.save_change(
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
                    raise ConflictError("AccessGroup grant completion changed its operation.")

                result = AccessGroupActionGrantChangeResultDTO(
                    installation_id=facts.installation_id,
                    organization_id=facts.organization_id,
                    project_id=facts.project_id,
                    group_id=facts.group_id,
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
                await self._access_group_grant_writer.save_result(
                    result=result,
                    before_revision=facts.access_revision,
                    before_can_grant=before.can_grant,
                )
                return result
        except TimeoutError as error:
            raise DependencyUnavailableError() from error

    @staticmethod
    def _require_recipient(
        facts: AccessGroupGrantManagementFactsDTO,
        command: SetAccessGroupActionGrantCommand | RemoveAccessGroupActionGrantCommand,
    ) -> None:
        """Check fresh target scope, applying account eligibility only to new assignments."""
        recipient = facts.recipient
        if recipient is None:
            raise ResourceNotFoundError()
        if (
            recipient.id != command.recipient_principal_id
            or recipient.organization_id != facts.organization_id
        ):
            raise RuntimeError("AccessGroup grant facts changed the recipient scope.")
        if recipient.kind is PrincipalKind.APPLICATION and not facts.recipient_application_is_bound:
            raise ResourceNotFoundError()
        if (
            isinstance(command, SetAccessGroupActionGrantCommand)
            and not facts.recipient_is_project_member
        ):
            raise ResourceNotFoundError()
        if not AccessGroupGrantPolicy.supports_recipient(
            action_id=command.action_id,
            kind=recipient.kind,
            can_grant=command.can_grant
            if isinstance(command, SetAccessGroupActionGrantCommand)
            else False,
        ):
            raise InvalidInputError(
                "This action and grant level do not support the recipient kind."
            )
        if isinstance(
            command, SetAccessGroupActionGrantCommand
        ) and not AccessGroupGrantPolicy.may_receive(
            recipient_access=PrincipalAccessPolicyInput(
                principal=recipient,
                has_pending_recovery=facts.recipient_has_pending_recovery,
                credential_is_current=True,
            ),
            is_project_member=facts.recipient_is_project_member,
            has_coherent_identity=facts.recipient_has_coherent_identity,
            application_is_bound=facts.recipient_application_is_bound,
        ):
            raise ConflictError("The recipient is not currently eligible for assignment.")

    @staticmethod
    def _require_safe_completed_operation(operation: object) -> CompletedSynchronousOperationDTO:
        """Require a safe synchronous completion before using its retained business receipt."""
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The AccessGroup grant has no safe original result.")
        return operation

    @staticmethod
    def _require_matching_original(
        facts: AccessGroupGrantManagementFactsDTO,
        command: SetAccessGroupActionGrantCommand | RemoveAccessGroupActionGrantCommand,
        completed: CompletedSynchronousOperationDTO,
        original: AccessGroupActionGrantChangeResultDTO,
    ) -> None:
        """Reject altered scope or outcome rather than redispatching uncertain original work."""
        setting = isinstance(command, SetAccessGroupActionGrantCommand)
        if (
            original.operation != completed
            or original.installation_id != facts.installation_id
            or original.organization_id != facts.organization_id
            or original.project_id != facts.project_id
            or original.group_id != facts.group_id
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
            raise ConflictError("The original AccessGroup grant result is incoherent.")
