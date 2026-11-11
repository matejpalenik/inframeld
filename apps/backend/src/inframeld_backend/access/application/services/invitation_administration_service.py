import asyncio
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.commands.revoke_invitation_command import (
    RevokeInvitationCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_facts_dto import InvitationFactsDTO
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_issue_result_dto import (
    InvitationIssueResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_revocation_facts_dto import (
    InvitationRevocationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.protocols.invitation_facts_reader import (
    InvitationFactsReader,
)
from inframeld_backend.access.application.protocols.invitation_issuer import InvitationIssuer
from inframeld_backend.access.application.protocols.invitation_revoker import InvitationRevoker
from inframeld_backend.access.application.protocols.invitation_writer import InvitationWriter
from inframeld_backend.access.application.services.invitation_fingerprint_service import (
    InvitationFingerprintService,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.access_group_grant_policy import (
    AccessGroupGrantPolicy,
)
from inframeld_backend.access.domain.policies.action_authorization_policy import (
    ActionAuthorizationPolicy,
)
from inframeld_backend.access.domain.policies.application_account_grant_policy import (
    ApplicationAccountGrantPolicy,
)
from inframeld_backend.access.domain.policies.human_admission_policy import HumanAdmissionPolicy
from inframeld_backend.access.domain.policies.invitation_policy import InvitationPolicy
from inframeld_backend.access.domain.policies.organization_grant_policy import (
    OrganizationGrantPolicy,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_action_eligibility_policy import (
    ProjectActionEligibilityPolicy,
)
from inframeld_backend.access.domain.policies.project_grant_delegation_policy import (
    ProjectGrantDelegationPolicy,
)
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
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


class InvitationAdministrationService(InvitationIssuer, InvitationRevoker):
    """Keep current administration authority ahead of retained-original disclosure."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        invitation_facts_reader: InvitationFactsReader,
        invitation_writer: InvitationWriter,
        operation_idempotency: OperationIdempotency,
        invitation_fingerprint_service: InvitationFingerprintService,
        default_lifetime_seconds: int,
        maximum_lifetime_seconds: int,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._invitation_facts_reader = invitation_facts_reader
        self._invitation_writer = invitation_writer
        self._operation_idempotency = operation_idempotency
        self._invitation_fingerprint_service = invitation_fingerprint_service
        self._default_lifetime_seconds = default_lifetime_seconds
        self._maximum_lifetime_seconds = maximum_lifetime_seconds

    @override
    async def revoke(
        self,
        *,
        access: AccessContextDTO,
        command: RevokeInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationRevocationResultDTO:
        route = f"/v1/invitations/{command.invitation_id.value}/revoke"
        if context.method != HttpMethod.POST or context.requested_route != route:
            raise RuntimeError("Invitation revocation changed its original method or route.")
        fingerprint = self._invitation_fingerprint_service.for_revoke(command)
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._invitation_facts_reader.lock_for_revocation(
                    access=access, invitation_id=command.invitation_id
                )
                if facts is None:
                    raise ResourceNotFoundError()
                self._authorize_revocation(access, command, facts)
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.SAFE_RESULT,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._completion(
                        operation, created=False, replay_kind=OperationReplayKind.SAFE_RESULT
                    )
                    original = await self._invitation_facts_reader.read_revocation_original(
                        organization_id=facts.organization_id,
                        actor_principal_id=access.actor_principal_id,
                        invitation_id=command.invitation_id,
                        operation_id=completed.operation_id,
                    )
                    if original is None:
                        raise DependencyUnavailableError()
                    if (
                        original.invitation_id != command.invitation_id
                        or original.organization_id != facts.organization_id
                        or original.operation != completed
                    ):
                        raise RuntimeError("The original revocation changed its checked binding.")
                    RevisionValidation.require(original.access_revision)
                    return original

                revision = facts.actor.access_revision
                if command.expected_access_revision != revision:
                    raise StaleRevisionError()
                changed = facts.invitation.revoked_at is None
                if changed and revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Organization revision cannot advance.")
                completed = self._completion(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.SAFE_RESULT
                    ),
                    created=True,
                    replay_kind=OperationReplayKind.SAFE_RESULT,
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Revocation completion changed its original operation.")
                result = InvitationRevocationResultDTO(
                    invitation_id=command.invitation_id,
                    organization_id=facts.organization_id,
                    access_revision=revision + int(changed),
                    operation=completed,
                )
                await self._invitation_writer.save_revocation(
                    invitation=facts.invitation,
                    result=result,
                    actor_principal_id=access.actor_principal_id,
                    expected_access_revision=revision,
                    revoked_at=facts.invitation.revoked_at or datetime.now(UTC),
                )
                return result
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _authorize_revocation(
        access: AccessContextDTO,
        command: RevokeInvitationCommand,
        facts: InvitationRevocationFactsDTO,
    ) -> None:
        actor = facts.actor
        if actor.principal.id != access.actor_principal_id:
            raise RuntimeError("Revocation facts changed the authenticated actor.")
        if facts.invitation.invitation_id != command.invitation_id:
            raise RuntimeError("Revocation facts changed the requested invitation.")
        if (
            facts.organization_id != facts.invitation.organization_id
            or actor.principal.organization_id != facts.organization_id
        ):
            raise ResourceNotFoundError()
        if actor.principal.kind is not PrincipalKind.HUMAN:
            raise AccessDeniedError()
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=actor.principal,
            has_pending_recovery=actor.has_pending_recovery,
            oauth_credential_facts=actor.oauth_credential_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        admission_grants = tuple(
            grant
            for grant in actor.grants
            if grant.action_id.value == OrganizationAction.ADMIT_USERS.value
        )
        if not InvitationPolicy.may_revoke(
            eligibility,
            organization_id=facts.organization_id,
            issuer_principal_id=facts.invitation.issuer_principal_id,
            has_admit_users=bool(admission_grants),
            can_grant_admit_users=any(grant.can_grant for grant in admission_grants),
        ):
            raise AccessDeniedError()
        RevisionValidation.require(actor.access_revision)

    @override
    async def issue(
        self,
        *,
        access: AccessContextDTO,
        command: IssueInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationIssueResultDTO:
        if context.method != HttpMethod.POST or context.requested_route != "/v1/invitations":
            raise RuntimeError("Invitation issuance changed its original method or route.")
        fingerprint = self._invitation_fingerprint_service.for_issue(command)
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._invitation_facts_reader.lock_for_issue(
                    access=access, command=command
                )
                if facts is None:
                    raise ResourceNotFoundError()
                self._authorize_issue(access, command, facts)
                operation = await self._operation_idempotency.reserve_or_recover(
                    context=context,
                    access=access,
                    authorization=facts,
                    fingerprint=fingerprint,
                    expected_replay_kind=OperationReplayKind.ISSUED_SECRET,
                )
                if not isinstance(operation, NewOperationReservationDTO):
                    completed = self._completion(operation, created=False)
                    original = await self._invitation_facts_reader.read_issue_original(
                        organization_id=command.organization_id,
                        issuer_principal_id=access.actor_principal_id,
                        operation_id=completed.operation_id,
                    )
                    if original is None:
                        raise DependencyUnavailableError()
                    if (
                        original.organization_id != command.organization_id
                        or original.issuer_principal_id != access.actor_principal_id
                        or original.issued_operation_id != completed.operation_id
                        or original.assignments != command.assignments
                    ):
                        raise RuntimeError("The original invitation changed its checked binding.")
                    return self._issue_result(original, completed, token=None)

                if command.expected_access_revision != facts.actor.access_revision:
                    raise StaleRevisionError()
                projects = self._project_revisions(facts)
                reviewed = {
                    item.project_id: item.access_revision
                    for item in command.expected_project_access_revisions
                }
                if reviewed.keys() != projects.keys():
                    raise InvalidInputError("Review every affected Project exactly once.")
                if reviewed != projects:
                    raise StaleRevisionError()
                if facts.actor.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Organization Access revision cannot advance.")
                lifetime = (
                    self._default_lifetime_seconds
                    if command.expires_in_seconds is None
                    else command.expires_in_seconds
                )
                if not 0 < lifetime <= self._maximum_lifetime_seconds:
                    raise InvalidInputError(
                        "The requested invitation lifetime exceeds its configured bound."
                    )
                issued_at = datetime.now(UTC)
                try:
                    expires_at = issued_at + timedelta(seconds=lifetime)
                except OverflowError:
                    raise InvalidInputError(
                        "The invitation expiry cannot be represented."
                    ) from None
                token = InvitationToken.generate()
                record = InvitationRecordDTO(
                    invitation_id=InvitationId(uuid4()),
                    organization_id=command.organization_id,
                    issuer_principal_id=access.actor_principal_id,
                    digest=token.digest(),
                    assignments=command.assignments,
                    issued_operation_id=operation.operation_id,
                    issued_access_revision=facts.actor.access_revision + 1,
                    issued_at=issued_at,
                    expires_at=expires_at,
                )
                await self._invitation_writer.save_issue(
                    record=record, expected_access_revision=facts.actor.access_revision
                )
                completed = self._completion(
                    await self._operation_idempotency.record_completed_result(
                        operation, replay_kind=OperationReplayKind.ISSUED_SECRET
                    ),
                    created=True,
                )
                if completed.operation_id != operation.operation_id:
                    raise RuntimeError("Invitation completion changed its original operation.")
                return self._issue_result(record, completed, token=token)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _completion(
        value: object,
        *,
        created: bool,
        replay_kind: OperationReplayKind = OperationReplayKind.ISSUED_SECRET,
    ) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(value, CompletedSynchronousOperationDTO)
            or value.replay_kind is not replay_kind
            or value.created is not created
            or value.expires_at.utcoffset() is None
        ):
            raise ConflictError("The invitation has no coherent completed outcome.")
        return value

    @staticmethod
    def _issue_result(
        record: InvitationRecordDTO,
        operation: CompletedSynchronousOperationDTO,
        *,
        token: InvitationToken | None,
    ) -> InvitationIssueResultDTO:
        return InvitationIssueResultDTO(
            invitation_id=record.invitation_id,
            organization_id=record.organization_id,
            assignments=record.assignments,
            expires_at=record.expires_at,
            access_revision=record.issued_access_revision,
            operation=operation,
            token=token,
        )

    @staticmethod
    def _project_revisions(facts: InvitationFactsDTO) -> dict[ProjectId, int]:
        revisions: dict[ProjectId, int] = {}
        for assignment in facts.assignments:
            project = assignment.project
            if project is None:
                continue
            previous = revisions.setdefault(project.project_id, project.access_revision)
            if previous != project.access_revision:
                raise RuntimeError("Invitation observations disagree on a Project revision.")
        return revisions

    @staticmethod
    def _authorize_issue(
        access: AccessContextDTO, command: IssueInvitationCommand, facts: InvitationFactsDTO
    ) -> None:
        actor = facts.actor
        if actor.principal.id != access.actor_principal_id:
            raise RuntimeError("Invitation facts changed the authenticated issuer.")
        if (
            facts.organization_id != command.organization_id
            or actor.principal.organization_id != command.organization_id
        ):
            raise ResourceNotFoundError()
        if actor.principal.kind is not PrincipalKind.HUMAN:
            raise AccessDeniedError()
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=actor.principal,
            has_pending_recovery=actor.has_pending_recovery,
            oauth_credential_facts=actor.oauth_credential_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        if not HumanAdmissionPolicy.may_authorize(
            eligibility,
            has_admit_users=any(
                grant.action_id.value == OrganizationAction.ADMIT_USERS.value
                for grant in actor.grants
            ),
        ):
            raise AccessDeniedError()
        RevisionValidation.require(actor.access_revision)
        if tuple(item.intent for item in facts.assignments) != command.assignments:
            raise RuntimeError("Invitation observations changed or reduced the intended effects.")
        for observed in facts.assignments:
            intent = observed.intent
            if not observed.target_exists:
                raise ResourceNotFoundError()
            if isinstance(intent, InvitationAdmissionOnlyIntentDTO):
                if observed.project is not None:
                    raise RuntimeError("Admission-only intent gained a Project scope.")
                continue
            if isinstance(intent, InvitationActionGrantIntentDTO) and isinstance(
                intent.target, OrganizationGrantTargetDTO
            ):
                if intent.target.organization_id != command.organization_id:
                    raise ResourceNotFoundError()
                if observed.project is not None:
                    raise RuntimeError("Organization intent gained a Project scope.")
                if not OrganizationGrantPolicy.supports_action(intent.action_id):
                    raise InvalidInputError()
                if not OrganizationGrantPolicy.may_manage(
                    actor_access=eligibility,
                    can_grant_action=any(
                        grant.action_id == intent.action_id and grant.can_grant
                        for grant in actor.grants
                    ),
                ):
                    raise AccessDeniedError()
                continue
            if isinstance(intent, InvitationActionGrantIntentDTO):
                if not isinstance(
                    intent.target,
                    (
                        ProjectGrantTargetDTO,
                        AccessGroupGrantTargetDTO,
                        ApplicationAccountGrantTargetDTO,
                    ),
                ):
                    raise ConflictError("The invitation target's receiving owner is not available.")
                requested_project = intent.target.project_id
            else:
                requested_project = intent.project_id
            project = observed.project
            if project is None:
                raise ResourceNotFoundError()
            if (
                project.project_id != requested_project
                or project.organization_id != command.organization_id
                or project.action.principal.id != access.actor_principal_id
                or project.action.principal.organization_id != command.organization_id
            ):
                raise RuntimeError("Invitation facts changed an intended Project binding.")
            RevisionValidation.require(project.access_revision)
            current = PrincipalAccessEvaluationService.evaluate(
                access=access,
                principal=project.action.principal,
                has_pending_recovery=project.action.has_pending_recovery,
                oauth_credential_facts=project.action.oauth_credential_facts,
            )
            PrincipalAccessEvaluationService.require_current_credential(
                access=access, principal_access=current
            )
            if not PrincipalAccessPolicy.may_use_product(current):
                raise AccessDeniedError()
            if not ProjectVisibilityPolicy.may_view_project(
                principal_status=project.action.principal.status,
                project_status=project.action.project_status,
                is_project_member=project.action.is_project_member,
            ):
                raise ResourceNotFoundError()
            if isinstance(intent, InvitationProjectMembershipIntentDTO):
                allowed = ActionAuthorizationPolicy.may_perform_action(
                    ActionAuthorizationPolicyInput(
                        principal_access=current,
                        is_project_member=project.action.is_project_member,
                        has_exact_action_grant=project.action.has_exact_action_grant,
                    )
                )
            elif isinstance(
                intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
            ):
                allowed = AccessGroupGrantPolicy.may_manage(
                    actor_access=current,
                    is_project_member=project.action.is_project_member,
                    can_grant_action=False,
                    is_group_member=observed.actor_is_group_member,
                    is_group_manager=observed.actor_is_group_manager,
                )
            elif isinstance(intent.target, AccessGroupGrantTargetDTO):
                if not AccessGroupGrantPolicy.supports_recipient(
                    action_id=intent.action_id, kind=PrincipalKind.HUMAN, can_grant=intent.can_grant
                ):
                    raise InvalidInputError()
                allowed = AccessGroupGrantPolicy.may_manage(
                    actor_access=current,
                    is_project_member=project.action.is_project_member,
                    can_grant_action=observed.actor_can_grant,
                    is_group_member=observed.actor_is_group_member,
                    is_group_manager=observed.actor_is_group_manager,
                )
            else:
                supported = (
                    ProjectActionEligibilityPolicy.may_use(
                        action_id=intent.action_id, principal_kind=PrincipalKind.HUMAN
                    )
                    if isinstance(intent.target, ProjectGrantTargetDTO)
                    else ApplicationAccountGrantPolicy.supports_recipient(
                        action_id=intent.action_id, kind=PrincipalKind.HUMAN
                    )
                )
                if not supported:
                    raise InvalidInputError()
                allowed = ProjectGrantDelegationPolicy.may_delegate_project_action(
                    actor_access=current,
                    actor_is_project_member=project.action.is_project_member,
                    actor_can_grant_action=observed.actor_can_grant,
                )
            if not allowed:
                raise AccessDeniedError()
