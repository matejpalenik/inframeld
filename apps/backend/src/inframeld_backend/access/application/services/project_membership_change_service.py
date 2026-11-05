import asyncio
from typing import override

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_departure_responsibility_dto import (
    ProjectDepartureResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)
from inframeld_backend.access.application.enums.project_membership_change_kind import (
    ProjectMembershipChangeKind,
)
from inframeld_backend.access.application.protocols.project_membership_change_facts_reader import (
    ProjectMembershipChangeFactsReader,
)
from inframeld_backend.access.application.protocols.project_membership_change_result_reader import (
    ProjectMembershipChangeResultReader,
)
from inframeld_backend.access.application.protocols.project_membership_change_writer import (
    ProjectMembershipChangeWriter,
)
from inframeld_backend.access.application.protocols.project_membership_changer import (
    ProjectMembershipChanger,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.project_membership_change_fingerprint_service import (
    ProjectMembershipChangeFingerprintService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
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
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
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
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


class ProjectMembershipChangeService(ProjectMembershipChanger):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        membership_facts_reader: ProjectMembershipChangeFactsReader,
        membership_change_writer: ProjectMembershipChangeWriter,
        membership_result_reader: ProjectMembershipChangeResultReader,
        operation_idempotency: OperationIdempotency,
        membership_fingerprint_service: ProjectMembershipChangeFingerprintService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._membership_facts_reader = membership_facts_reader
        self._membership_change_writer = membership_change_writer
        self._membership_result_reader = membership_result_reader
        self._operation_idempotency = operation_idempotency
        self._membership_fingerprint_service = membership_fingerprint_service

    @override
    async def add_member(
        self,
        *,
        access: AccessContextDTO,
        command: AddProjectMemberCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        return await self._change(
            access=access,
            command=command,
            context=context,
            change_kind=ProjectMembershipChangeKind.ADD,
            fingerprint=self._membership_fingerprint_service.for_add(command),
        )

    @override
    async def remove_member(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectMemberCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        return await self._change(
            access=access,
            command=command,
            context=context,
            change_kind=ProjectMembershipChangeKind.REMOVE,
            fingerprint=self._membership_fingerprint_service.for_remove(command),
        )

    async def _change(
        self,
        *,
        access: AccessContextDTO,
        command: AddProjectMemberCommand | RemoveProjectMemberCommand,
        context: IdempotencyContextDTO,
        change_kind: ProjectMembershipChangeKind,
        fingerprint: RequestFingerprint,
    ) -> ProjectMembershipChangeResultDTO:
        method = change_kind.http_method
        route = f"/v1/projects/{command.project_id.value}/members/{command.principal_id.value}"
        if context.method != method or context.requested_route != route:
            raise RuntimeError("Membership change altered its original method or route.")

        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts, scope = await self._lock_and_authorize(access, command)
                operation = await self._reserve_or_recover(
                    context=context, access=access, scope=scope, fingerprint=fingerprint
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    return await self._load_original_membership_result(
                        facts=facts, command=command, change_kind=change_kind, operation=operation
                    )

                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                self._require_recipient(facts, command, change_kind)
                if (
                    change_kind is ProjectMembershipChangeKind.REMOVE
                    and facts.recipient_is_project_member
                ):
                    responsibilities = (
                        await self._membership_facts_reader.load_departure_responsibilities(
                            facts=facts, principal_id=command.principal_id
                        )
                    )
                    self._require_handover(facts, responsibilities)
                changed = (
                    not facts.recipient_is_project_member
                    if change_kind is ProjectMembershipChangeKind.ADD
                    else facts.recipient_is_project_member
                )
                await self._membership_change_writer.save(
                    facts=facts,
                    principal_id=command.principal_id,
                    change_kind=change_kind,
                    operation_id=operation.operation_id,
                )
                completed = self._completed(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Membership completion changed the original operation.")
                return ProjectMembershipChangeResultDTO(
                    facts.installation_id,
                    scope.organization_id,
                    scope.project_id,
                    access.actor_principal_id,
                    command.principal_id,
                    change_kind,
                    facts.access_revision + int(changed),
                    changed,
                    change_kind.success_status(changed=changed),
                    completed,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    async def _lock_and_authorize(
        self,
        access: AccessContextDTO,
        command: AddProjectMemberCommand | RemoveProjectMemberCommand,
    ) -> tuple[ProjectMembershipChangeFactsDTO, ProjectActionAuthorizationDTO]:
        facts = await self._membership_facts_reader.lock_and_load_membership_state(
            access=access, project_id=command.project_id, principal_id=command.principal_id
        )
        facts = ProjectMembershipObservationDTO.require_requested_scope(
            observation=facts,
            actor_principal_id=access.actor_principal_id,
            project_id=command.project_id,
        )

        ActionAuthorizationService.require_authorization_from_facts(
            access=access, facts=facts.action
        )
        if not ProjectActionEligibilityPolicy.may_use(
            action_id=ActionId(ProjectAction.MANAGE_PROJECT_MEMBERS.value),
            principal_kind=facts.action.principal.kind,
        ):
            raise AccessDeniedError()

        return facts, ProjectActionAuthorizationDTO(facts.organization_id, facts.project_id)

    async def _reserve_or_recover(
        self,
        *,
        context: IdempotencyContextDTO,
        access: AccessContextDTO,
        scope: ProjectActionAuthorizationDTO,
        fingerprint: RequestFingerprint,
    ) -> NewOperationReservationDTO | CompletedSynchronousOperationDTO:
        operation = await self._operation_idempotency.reserve_or_recover(
            context=context,
            access=access,
            authorization=scope,
            fingerprint=fingerprint,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            lookup_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                ActionId(ProjectAction.MANAGE_PROJECT_MEMBERS.value),
            ),
        )
        return (
            operation
            if isinstance(operation, NewOperationReservationDTO)
            else self._completed(operation)
        )

    async def _load_original_membership_result(
        self,
        *,
        facts: ProjectMembershipChangeFactsDTO,
        command: AddProjectMemberCommand | RemoveProjectMemberCommand,
        change_kind: ProjectMembershipChangeKind,
        operation: CompletedSynchronousOperationDTO,
    ) -> ProjectMembershipChangeResultDTO:
        original = await self._membership_result_reader.load_original_membership_result(
            facts=facts,
            principal_id=command.principal_id,
            change_kind=change_kind,
            operation=operation,
        )
        if (
            original.operation != operation
            or original.installation_id != facts.installation_id
            or original.organization_id != facts.organization_id
            or original.project_id != facts.project_id
            or original.actor_principal_id != facts.action.principal.id
            or original.principal_id != command.principal_id
            or original.change_kind is not change_kind
            or original.access_revision < 0
            or original.status_code != change_kind.success_status(changed=original.changed)
        ):
            raise ConflictError("The original membership result is incoherent.")
        return original

    @staticmethod
    def _require_recipient(
        facts: ProjectMembershipChangeFactsDTO,
        command: AddProjectMemberCommand | RemoveProjectMemberCommand,
        change_kind: ProjectMembershipChangeKind,
    ) -> None:
        recipient = facts.recipient
        if recipient is None:
            raise ResourceNotFoundError()
        if (
            recipient.id != command.principal_id
            or recipient.organization_id != facts.organization_id
        ):
            raise RuntimeError("Membership facts changed the requested recipient scope.")
        if recipient.kind is not PrincipalKind.HUMAN:
            raise InvalidInputError("Project membership changes require an admitted human.")
        if change_kind is ProjectMembershipChangeKind.ADD and (
            not facts.recipient_has_coherent_identity
            or not PrincipalAccessPolicy.may_use_product(
                PrincipalAccessPolicyInput(recipient, facts.recipient_has_pending_recovery, True)
            )
        ):
            raise ConflictError("The requested human is not currently eligible to join.")

    @staticmethod
    def _require_handover(
        facts: ProjectMembershipChangeFactsDTO,
        responsibilities: tuple[ProjectDepartureResponsibilityDTO, ...],
    ) -> None:
        for item in responsibilities:
            if item.target_kind == "project" and item.target_id != facts.project_id.value:
                raise RuntimeError("Departure facts changed the checked Project responsibility.")

        policy_inputs = tuple(
            ProjectDepartureResponsibilityPolicyInput(
                item.target_kind,
                item.action_id,
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
                    for candidate in item.candidates
                ),
            )
            for item in responsibilities
        )
        if not ProjectDeparturePolicy.may_depart(policy_inputs):
            raise ConflictError(
                "The departure would leave a responsibility without an eligible human."
            )

    @staticmethod
    def _completed(operation: object) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("Membership change has no safe completed result.")
        return operation
