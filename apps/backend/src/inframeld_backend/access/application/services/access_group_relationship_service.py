import asyncio
from json import dumps
from typing import override

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.protocols.access_group_change_facts_reader import (
    AccessGroupChangeFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_relationship_changer import (
    AccessGroupRelationshipChanger,
)
from inframeld_backend.access.application.protocols.access_group_relationship_result_reader import (
    AccessGroupRelationshipResultReader,
)
from inframeld_backend.access.application.protocols.access_group_relationship_writer import (
    AccessGroupRelationshipWriter,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
from inframeld_backend.access.domain.policies.access_group_relationship_policy import (
    AccessGroupRelationshipPolicy,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_departure_policy import ProjectDeparturePolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_responsibility_policy_input import (
    ProjectDepartureResponsibilityPolicyInput,
)
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class AccessGroupRelationshipService(AccessGroupRelationshipChanger):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        facts_reader: AccessGroupChangeFactsReader,
        writer: AccessGroupRelationshipWriter,
        result_reader: AccessGroupRelationshipResultReader,
        operation_idempotency: OperationIdempotency,
        request_fingerprint_service: RequestFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._facts_reader = facts_reader
        self._writer = writer
        self._result_reader = result_reader
        self._operation_idempotency = operation_idempotency
        self._request_fingerprint_service = request_fingerprint_service

    @override
    async def change(
        self,
        *,
        access: AccessContextDTO,
        command: ChangeAccessGroupRelationshipCommand,
        context: IdempotencyContextDTO,
    ) -> AccessGroupRelationshipResultDTO:
        kind = command.change_kind
        route = f"/v1/projects/{command.project_id.value}/access-groups/{command.group_id.value}/{kind.collection}/{command.principal_id.value}"
        if context.method != kind.http_method or context.requested_route != route:
            raise RuntimeError("Group change altered its original method or route.")
        fingerprint = self._request_fingerprint_service.fingerprint(
            purpose="access.group.relationship:v1",
            canonical_request=dumps(
                {
                    "projectId": str(command.project_id.value),
                    "groupId": str(command.group_id.value),
                    "principalId": str(command.principal_id.value),
                    "change": kind.value,
                    "expectedAccessRevision": command.expected_access_revision,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
        )
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._facts_reader.lock_for_change(access=access, command=command)
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.project_id != command.project_id
                    or facts.group_id != command.group_id
                    or facts.action.principal.id != access.actor_principal_id
                    or facts.organization_id != facts.action.principal.organization_id
                ):
                    raise RuntimeError("Group change facts altered the requested actor or scope.")
                RevisionValidation.require(facts.access_revision)
                ActionAuthorizationService.require_authorization_from_facts(
                    access=access, facts=facts.action
                )
                if facts.action.principal.kind is not PrincipalKind.HUMAN:
                    raise AccessDeniedError()
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._completed(operation)
                    original = await self._result_reader.original(
                        facts=facts, command=command, operation=completed
                    )
                    if (
                        original.operation != completed
                        or original.organization_id != facts.organization_id
                        or original.project_id != command.project_id
                        or original.group_id != command.group_id
                        or original.actor_principal_id != access.actor_principal_id
                        or original.principal_id != command.principal_id
                        or original.change_kind is not kind
                        or self._transition(kind, original.relationships) != original.relationships
                        or original.status_code != kind.success_status(changed=original.changed)
                        or original.access_revision
                        != command.expected_access_revision + int(original.changed)
                    ):
                        raise ConflictError("The original group transition is incoherent.")
                    return original
                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                self._require_recipient(facts, command)
                before = facts.relationships
                after = self._transition(kind, before)
                if before.manager and not after.manager:
                    candidates = await self._facts_reader.remaining_managers(
                        facts=facts, command=command
                    )
                    if any(
                        candidate.principal.id == command.principal_id for candidate in candidates
                    ):
                        raise RuntimeError("Handover included the departing manager.")
                    responsibility = ProjectDepartureResponsibilityPolicyInput(
                        ProjectDepartureTargetKind.ACCESS_GROUP,
                        None,
                        tuple(
                            ProjectDepartureCandidatePolicyInput(
                                candidate.principal,
                                candidate.has_pending_recovery,
                                candidate.is_project_member,
                                candidate.has_coherent_identity,
                                candidate.can_grant,
                                candidate.is_group_member,
                                candidate.is_group_manager,
                            )
                            for candidate in candidates
                        ),
                    )
                    if not ProjectDeparturePolicy.may_depart((responsibility,)):
                        raise ConflictError("The group must retain an eligible human manager.")
                changed = before != after
                if changed and facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project Access revision cannot advance.")
                await self._writer.save(
                    facts=facts, command=command, operation_id=operation.operation_id, after=after
                )
                completed = self._completed(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Group completion changed its original operation.")
                return AccessGroupRelationshipResultDTO(
                    facts.organization_id,
                    facts.project_id,
                    facts.group_id,
                    access.actor_principal_id,
                    command.principal_id,
                    kind,
                    facts.access_revision + int(changed),
                    changed,
                    after,
                    kind.success_status(changed=changed),
                    completed,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _require_recipient(
        facts: AccessGroupChangeFactsDTO, command: ChangeAccessGroupRelationshipCommand
    ) -> None:
        recipient = facts.recipient
        if recipient is None:
            raise ResourceNotFoundError()
        if (
            recipient.id != command.principal_id
            or recipient.organization_id != facts.organization_id
        ):
            raise RuntimeError("Group facts changed the requested recipient.")
        if (
            command.change_kind
            in (AccessGroupChangeKind.APPOINT_MANAGER, AccessGroupChangeKind.REMOVE_MANAGER)
            and recipient.kind is not PrincipalKind.HUMAN
        ):
            raise InvalidInputError("Only an eligible human can manage an access group.")
        if command.change_kind.is_addition and (
            not facts.recipient_is_project_member
            or (recipient.kind is PrincipalKind.HUMAN and not facts.recipient_has_coherent_identity)
            or not PrincipalAccessPolicy.may_use_product(
                PrincipalAccessPolicyInput(recipient, facts.recipient_has_pending_recovery, True)
            )
        ):
            raise ConflictError("The recipient is not an eligible current Project member.")

    @staticmethod
    def _transition(
        kind: AccessGroupChangeKind, before: AccessGroupRelationships
    ) -> AccessGroupRelationships:
        match kind:
            case AccessGroupChangeKind.ADD_MEMBER:
                return AccessGroupRelationshipPolicy.add_member(before)
            case AccessGroupChangeKind.REMOVE_MEMBER:
                return AccessGroupRelationshipPolicy.remove_member(before)
            case AccessGroupChangeKind.APPOINT_MANAGER:
                return AccessGroupRelationshipPolicy.appoint_manager(before)
            case AccessGroupChangeKind.REMOVE_MANAGER:
                return AccessGroupRelationshipPolicy.remove_manager(before)

    @staticmethod
    def _completed(operation: object) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The group transition has no safe original result.")
        return operation
