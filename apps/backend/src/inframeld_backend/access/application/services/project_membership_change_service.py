import asyncio
from typing import Literal, override

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
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_result_dto import (
    ProjectMembershipChangeResultDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
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
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.services.project_membership_change_fingerprint_service import (
    ProjectMembershipChangeFingerprintService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.policies.project_departure_policy import ProjectDeparturePolicy
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
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
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
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
        transactions: TransactionManager,
        facts: ProjectMembershipChangeFactsReader,
        writer: ProjectMembershipChangeWriter,
        results: ProjectMembershipChangeResultReader,
        idempotency: OperationIdempotency,
        fingerprints: ProjectMembershipChangeFingerprintService,
    ) -> None:
        self._transactions = transactions
        self._facts = facts
        self._writer = writer
        self._results = results
        self._idempotency = idempotency
        self._fingerprints = fingerprints

    @override
    async def add_member(
        self,
        *,
        access: AccessContextDTO,
        command: AddProjectMemberCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        return await self._change(
            access=access,
            command=command,
            context=context,
            change_kind="add",
            fingerprint=self._fingerprints.for_add(command),
        )

    @override
    async def remove_member(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectMemberCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectMembershipChangeResultDTO:
        return await self._change(
            access=access,
            command=command,
            context=context,
            change_kind="remove",
            fingerprint=self._fingerprints.for_remove(command),
        )

    async def _change(
        self,
        *,
        access: AccessContextDTO,
        command: AddProjectMemberCommand | RemoveProjectMemberCommand,
        context: OperationAdmissionContextDTO,
        change_kind: Literal["add", "remove"],
        fingerprint: RequestFingerprint,
    ) -> ProjectMembershipChangeResultDTO:
        method = "PUT" if change_kind == "add" else "DELETE"
        route = f"/v1/projects/{command.project_id.value}/members/{command.principal_id.value}"
        if context.method != method or context.requested_route != route:
            raise RuntimeError("Membership change altered its original method or route.")

        try:
            async with asyncio.timeout(5), self._transactions.begin():
                facts = await self._facts.read_for_change(
                    access=access,
                    project_id=command.project_id,
                    principal_id=command.principal_id,
                    removing=change_kind == "remove",
                )
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.project_id != command.project_id
                    or facts.action.principal.id != access.actor_principal_id
                    or facts.action.principal.organization_id != facts.organization_id
                    or facts.access_revision < 0
                ):
                    raise RuntimeError("Membership facts changed the actor or requested scope.")
                scope = self._authorize(access, facts)
                operation = await self._idempotency.find_or_reserve(
                    context=context,
                    access=access,
                    authorization=scope,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                        ActionId("manage-project-members"),
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._completed(operation)
                    original = await self._results.original(
                        facts=facts,
                        principal_id=command.principal_id,
                        change_kind=change_kind,
                        operation=completed,
                    )
                    if (
                        original.operation != completed
                        or original.installation_id != facts.installation_id
                        or original.organization_id != scope.organization_id
                        or original.project_id != scope.project_id
                        or original.actor_principal_id != access.actor_principal_id
                        or original.principal_id != command.principal_id
                        or original.change_kind != change_kind
                        or original.access_revision < 0
                        or original.status_code
                        != (201 if change_kind == "add" and original.changed else 200)
                    ):
                        raise ConflictError("The original membership result is incoherent.")
                    return original

                if command.expected_access_revision != facts.access_revision:
                    raise StaleRevisionError()
                self._require_recipient(facts, command, change_kind)
                if change_kind == "remove" and facts.recipient_is_project_member:
                    self._require_handover(facts)
                changed = (
                    not facts.recipient_is_project_member
                    if change_kind == "add"
                    else facts.recipient_is_project_member
                )
                await self._writer.save(
                    facts=facts,
                    principal_id=command.principal_id,
                    change_kind=change_kind,
                    operation_id=operation.operation_id,
                )
                completed = self._completed(
                    await self._idempotency.record_completed_result(
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
                    201 if change_kind == "add" and changed else 200,
                    completed,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _authorize(
        access: AccessContextDTO, facts: ProjectMembershipChangeFactsDTO
    ) -> ProjectActionAuthorizationDTO:
        action = facts.action
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=action.principal,
            has_pending_recovery=action.has_pending_recovery,
            oauth_credential_facts=action.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=action.principal.status,
            project_status=action.project_status,
            is_project_member=action.is_project_member,
        ):
            raise ResourceNotFoundError()
        if (
            not PrincipalAccessPolicy.may_use_product(eligibility)
            or not ProjectActionEligibilityPolicy.may_use(
                action_id=ActionId("manage-project-members"), principal_kind=action.principal.kind
            )
            or not action.has_exact_action_grant
        ):
            raise AccessDeniedError()
        return ProjectActionAuthorizationDTO(facts.organization_id, facts.project_id)

    @staticmethod
    def _require_recipient(
        facts: ProjectMembershipChangeFactsDTO,
        command: AddProjectMemberCommand | RemoveProjectMemberCommand,
        change_kind: Literal["add", "remove"],
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
        if change_kind == "add" and (
            not facts.recipient_has_coherent_identity
            or not PrincipalAccessPolicy.may_use_product(
                PrincipalAccessPolicyInput(recipient, facts.recipient_has_pending_recovery, True)
            )
        ):
            raise ConflictError("The requested human is not currently eligible to join.")

    @staticmethod
    def _require_handover(facts: ProjectMembershipChangeFactsDTO) -> None:
        for item in facts.responsibilities:
            if item.target_kind == "project" and item.target_id != facts.project_id.value:
                raise RuntimeError("Departure facts changed the checked Project responsibility.")
            if not ProjectDeparturePolicy.supports_responsibility(
                target_kind=item.target_kind,
                action_id=item.action_id,
                requires_group_manager=item.requires_group_manager,
            ):
                raise ConflictError("The stored departure responsibility is not supported.")
        responsibilities = tuple(
            ProjectDepartureResponsibilityPolicyInput(
                item.requires_group_manager,
                item.allows_group_manager,
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
            for item in facts.responsibilities
        )
        if not ProjectDeparturePolicy.may_depart(responsibilities):
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
