import asyncio
from typing import override

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.commands.remove_project_action_grant_command import (
    RemoveProjectActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_project_action_grant_command import (
    SetProjectActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_authorization_dto import (
    ProjectGrantAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.project_action_grant_result_reader import (
    ProjectActionGrantResultReader,
)
from inframeld_backend.access.application.protocols.project_action_grant_result_writer import (
    ProjectActionGrantResultWriter,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.application.protocols.project_grant_management_facts_reader import (
    ProjectGrantManagementFactsReader,
)
from inframeld_backend.access.application.protocols.project_membership_repository import (
    ProjectMembershipRepository,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
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
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
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


class ProjectGrantChangeService(ProjectGrantChanger):
    def __init__(
        self,
        transactions: TransactionManager,
        authorizer: ProjectGrantAuthorizer,
        idempotency: OperationIdempotency,
        memberships: ProjectMembershipRepository,
        fingerprints: ProjectGrantChangeFingerprintService,
        *,
        management_facts: ProjectGrantManagementFactsReader,
        results: ProjectActionGrantResultReader,
        result_writer: ProjectActionGrantResultWriter,
    ) -> None:
        self._transactions = transactions
        self._authorizer = authorizer
        self._idempotency = idempotency
        self._memberships = memberships
        self._fingerprints = fingerprints
        self._management_facts = management_facts
        self._results = results
        self._result_writer = result_writer

    @override
    async def set_action_grant(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectActionGrantCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        return await self._manage(
            access=access,
            command=command,
            context=context,
            fingerprint=self._fingerprints.for_set(command),
        )

    @override
    async def remove_action_grant(
        self,
        *,
        access: AccessContextDTO,
        command: RemoveProjectActionGrantCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectActionGrantChangeResultDTO:
        return await self._manage(
            access=access,
            command=command,
            context=context,
            fingerprint=self._fingerprints.for_remove(command),
        )

    async def _manage(
        self,
        *,
        access: AccessContextDTO,
        command: SetProjectActionGrantCommand | RemoveProjectActionGrantCommand,
        context: OperationAdmissionContextDTO,
        fingerprint: RequestFingerprint,
    ) -> ProjectActionGrantChangeResultDTO:
        setting = isinstance(command, SetProjectActionGrantCommand)
        method = "PUT" if setting else "DELETE"
        route = f"/v1/projects/{command.project_id.value}/grants/{command.recipient_principal_id.value}/{command.action_id.value}"
        if context.method != method or context.requested_route != route:
            raise RuntimeError("Grant management changed its original method or exact route.")
        if not ProjectActionEligibilityPolicy.may_use(
            action_id=command.action_id, principal_kind=PrincipalKind.HUMAN
        ):
            raise InvalidInputError("This action does not belong to the Project catalogue.")

        try:
            async with asyncio.timeout(5), self._transactions.begin():
                facts = await self._management_facts.read_for_management(
                    access=access,
                    project_id=command.project_id,
                    recipient_principal_id=command.recipient_principal_id,
                    action_id=command.action_id,
                )
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.project_id != command.project_id
                    or facts.action_id != command.action_id
                    or facts.grant.actor.id != access.actor_principal_id
                    or facts.grant.actor.organization_id != facts.organization_id
                    or type(facts.grant.project_access_revision) is not int
                    or not 0 <= facts.grant.project_access_revision <= 2**63 - 1
                ):
                    raise RuntimeError("Grant management facts changed actor, scope or revision.")
                scope = self._authorize_management(access, facts)
                operation = await self._idempotency.find_or_reserve(
                    context=context,
                    access=access,
                    authorization=scope,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                    lookup_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.PROJECT_GRANT_READ, command.action_id
                    ),
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._require_completed_result(operation)
                    original = await self._results.original(
                        facts=facts, command=command, context=context, operation=completed
                    )
                    self._require_original(facts, command, completed, original)
                    return original

                if command.expected_access_revision != scope.project_access_revision:
                    raise StaleRevisionError()
                recipient = facts.grant.recipient
                if recipient is None:
                    raise ResourceNotFoundError()
                if (
                    recipient.id != command.recipient_principal_id
                    or recipient.organization_id != facts.organization_id
                ):
                    raise RuntimeError(
                        "Grant management returned a recipient outside its exact scope."
                    )
                if (
                    recipient.kind is PrincipalKind.APPLICATION
                    and not facts.recipient_application_is_project_bound
                ):
                    raise ResourceNotFoundError()
                if isinstance(command, SetProjectActionGrantCommand) and (
                    not ProjectActionEligibilityPolicy.may_use(
                        action_id=command.action_id, principal_kind=recipient.kind
                    )
                    or (recipient.kind is PrincipalKind.APPLICATION and command.can_grant)
                ):
                    raise InvalidInputError(
                        "This recipient cannot hold the requested grant combination."
                    )
                if isinstance(
                    command, SetProjectActionGrantCommand
                ) and not ProjectGrantDelegationPolicy.may_assign_to_recipient(
                    recipient_access=PrincipalAccessPolicyInput(
                        recipient, facts.recipient_has_pending_recovery, True
                    ),
                    is_project_member=facts.grant.recipient_is_project_member,
                    has_coherent_identity=facts.recipient_has_coherent_identity,
                    application_is_project_bound=facts.recipient_application_is_project_bound,
                    action_id=command.action_id,
                    can_grant=command.can_grant,
                ):
                    raise ConflictError("The recipient is not currently eligible for assignment.")

                before_can_grant: bool | None = None
                changed = False
                if facts.grant.recipient_is_project_member:
                    membership = await self._memberships.get(
                        organization_id=scope.organization_id,
                        project_id=scope.project_id,
                        principal_id=command.recipient_principal_id,
                    )
                    if (
                        membership.organization_id != scope.organization_id
                        or membership.project_id != scope.project_id
                        or membership.principal_id != command.recipient_principal_id
                        or membership.principal_kind is not recipient.kind
                    ):
                        raise RuntimeError(
                            "The loaded membership changed the managed recipient or scope."
                        )
                    previous = next(
                        (x for x in membership.grants if x.action_id == command.action_id), None
                    )
                    if previous is not None:
                        before_can_grant = previous.level is ProjectGrantLevel.USE_AND_GRANT
                    after_can_grant = (
                        command.can_grant
                        if isinstance(command, SetProjectActionGrantCommand)
                        else None
                    )
                    if before_can_grant is True and after_can_grant is not True:
                        candidates = tuple(
                            candidate
                            for candidate in facts.other_grantors
                            if candidate.principal.id != command.recipient_principal_id
                        )
                        if any(
                            x.principal.organization_id != facts.organization_id for x in candidates
                        ):
                            raise RuntimeError(
                                "An alternate grantor belongs to another Organization."
                            )
                        if not ProjectDeparturePolicy.may_depart(
                            (ProjectDepartureResponsibilityPolicyInput(False, False, candidates),)
                        ):
                            raise ConflictError(
                                "The change would remove the last eligible exact-action grantor."
                            )
                    if (
                        before_can_grant != after_can_grant
                        and scope.project_access_revision == 2**63 - 1
                    ):
                        raise ConflictError("The Project Access revision cannot advance.")

                    if isinstance(command, SetProjectActionGrantCommand):
                        changed = membership.set_action_grant(
                            action_id=command.action_id,
                            level=ProjectGrantLevel.USE_AND_GRANT
                            if command.can_grant
                            else ProjectGrantLevel.USE_ONLY,
                            assigned_by_principal_id=access.actor_principal_id,
                        )
                    else:
                        changed = membership.remove_action_grant(action_id=command.action_id)
                    await self._memberships.save_action_grant_change(
                        membership,
                        action_id=command.action_id,
                        actor_principal_id=access.actor_principal_id,
                        expected_project_access_revision=scope.project_access_revision,
                        operation_id=operation.operation_id,
                    )

                completed = self._require_completed_result(
                    await self._idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                )
                if completed.operation_id != operation.operation_id:
                    raise ConflictError("Completion changed the original grant operation.")
                result = ProjectActionGrantChangeResultDTO(
                    facts.installation_id,
                    scope.organization_id,
                    scope.project_id,
                    access.actor_principal_id,
                    command.recipient_principal_id,
                    command.action_id,
                    "set" if setting else "remove",
                    command.can_grant
                    if isinstance(command, SetProjectActionGrantCommand)
                    else None,
                    scope.project_access_revision + int(changed),
                    changed,
                    201 if setting and before_can_grant is None and changed else 200,
                    completed,
                )
                await self._result_writer.save(
                    result,
                    before_revision=scope.project_access_revision,
                    before_can_grant=before_can_grant,
                )
                return result
        except TimeoutError as error:
            raise DependencyUnavailableError() from error

    @staticmethod
    def _authorize_management(
        access: AccessContextDTO, facts: ProjectActionGrantManagementFactsDTO
    ) -> ProjectGrantAuthorizationDTO:
        grant = facts.grant
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=grant.actor,
            has_pending_recovery=grant.has_pending_recovery,
            oauth_credential_facts=grant.oauth_credential_facts,
        )
        if not eligibility.credential_is_current:
            raise HumanOAuthCredentialRejectedError()
        if grant.actor.kind is not PrincipalKind.HUMAN or not PrincipalAccessPolicy.may_use_product(
            eligibility
        ):
            raise AccessDeniedError()
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=grant.actor.status,
            project_status=grant.project_status,
            is_project_member=grant.actor_is_project_member,
        ):
            raise ResourceNotFoundError()
        if not ProjectGrantDelegationPolicy.may_delegate_project_action(
            actor_access=eligibility,
            actor_is_project_member=grant.actor_is_project_member,
            actor_can_grant_action=grant.actor_can_grant_action,
        ):
            raise AccessDeniedError()
        return ProjectGrantAuthorizationDTO(
            facts.organization_id, facts.project_id, grant.project_access_revision
        )

    @staticmethod
    def _require_original(
        facts: ProjectActionGrantManagementFactsDTO,
        command: SetProjectActionGrantCommand | RemoveProjectActionGrantCommand,
        completed: CompletedSynchronousOperationDTO,
        original: ProjectActionGrantChangeResultDTO,
    ) -> None:
        setting = isinstance(command, SetProjectActionGrantCommand)
        if (
            original.operation != completed
            or original.installation_id != facts.installation_id
            or original.organization_id != facts.organization_id
            or original.project_id != facts.project_id
            or original.actor_principal_id != facts.grant.actor.id
            or original.recipient_principal_id != command.recipient_principal_id
            or original.action_id != command.action_id
            or original.change_kind != ("set" if setting else "remove")
            or original.can_grant
            != (command.can_grant if isinstance(command, SetProjectActionGrantCommand) else None)
            or type(original.access_revision) is not int
            or not 0 <= original.access_revision <= 2**63 - 1
            or type(original.changed) is not bool
            or original.status_code not in ({200, 201} if setting else {200})
            or (original.status_code == 201 and not original.changed)
        ):
            raise ConflictError("The original grant result is incoherent.")

    @override
    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        command: AssignProjectUseOnlyGrantCommand,
        context: OperationAdmissionContextDTO,
    ) -> CompletedSynchronousOperationDTO:
        fingerprint = self._fingerprints.for_assign_use_only(command)

        async with self._transactions.begin():
            authorization = await self._authorizer.require_authorization(
                access=access,
                request=ProjectUseOnlyGrantAuthorizationRequestDTO(
                    project_id=command.project_id,
                    recipient_principal_id=command.recipient_principal_id,
                    action_id=command.action_id,
                ),
            )

            if authorization.project_id != command.project_id:
                raise RuntimeError("Authorization returned a different project than requested.")

            operation = await self._idempotency.find_or_reserve(
                context=context,
                access=access,
                authorization=authorization,
                fingerprint=fingerprint,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                lookup_authority=OperationLookupAuthority(
                    OperationLookupAuthorityFamily.PROJECT_GRANT_READ, command.action_id
                ),
            )

            if not isinstance(operation, NewOperationReservationDTO):
                return self._require_completed_result(operation)

            # A replay keeps its original revision. Only new work checks current state.
            if authorization.project_access_revision != command.expected_access_revision:
                raise StaleRevisionError()

            membership = await self._memberships.get(
                organization_id=authorization.organization_id,
                project_id=authorization.project_id,
                principal_id=command.recipient_principal_id,
            )
            if (
                membership.organization_id != authorization.organization_id
                or membership.project_id != authorization.project_id
                or membership.principal_id != command.recipient_principal_id
            ):
                raise RuntimeError(
                    "The loaded membership does not match the authorized assignment."
                )

            try:
                membership.assign_use_only_grant(
                    action_id=command.action_id,
                    assigned_by_principal_id=access.actor_principal_id,
                )
            except ProjectGrantAlreadyExistsError as error:
                raise ConflictError("This project action grant already exists.") from error

            await self._memberships.save(
                membership,
                expected_project_access_revision=authorization.project_access_revision,
                operation_id=operation.operation_id,
            )
            completed = await self._idempotency.record_completed_result(
                operation, replay_kind=OperationReplayKind.SAFE_RESULT
            )
            return self._require_completed_result(completed)

    @staticmethod
    def _require_completed_result(
        operation: CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO,
    ) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The grant operation has no completed replay outcome.")
        return operation
