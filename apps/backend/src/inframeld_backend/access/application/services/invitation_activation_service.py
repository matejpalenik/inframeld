import asyncio
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.activate_invitation_command import (
    ActivateInvitationCommand,
)
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.protocols.invitation_activation_operation_store import (
    InvitationActivationOperationStore,
)
from inframeld_backend.access.application.protocols.invitation_activator import InvitationActivator
from inframeld_backend.access.application.protocols.invitation_admission_writer import (
    InvitationAdmissionWriter,
)
from inframeld_backend.access.application.protocols.invitation_assignment_facts_reader import (
    InvitationAssignmentFactsReader,
)
from inframeld_backend.access.application.services.invitation_assignment_service import (
    InvitationAssignmentService,
)
from inframeld_backend.access.application.services.invitation_fingerprint_service import (
    InvitationFingerprintService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policies.human_admission_policy import HumanAdmissionPolicy
from inframeld_backend.access.domain.policies.invitation_policy import InvitationPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class InvitationActivationService(InvitationActivator):
    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        invitation_assignment_facts_reader: InvitationAssignmentFactsReader,
        invitation_activation_operation_store: InvitationActivationOperationStore,
        invitation_fingerprint_service: InvitationFingerprintService,
        invitation_admission_writer: InvitationAdmissionWriter,
        invitation_assignment_service: InvitationAssignmentService,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._invitation_assignment_facts_reader = invitation_assignment_facts_reader
        self._invitation_activation_operation_store = invitation_activation_operation_store
        self._invitation_fingerprint_service = invitation_fingerprint_service
        self._invitation_admission_writer = invitation_admission_writer
        self._invitation_assignment_service = invitation_assignment_service

    @override
    async def activate(
        self,
        *,
        proof: InvitationBrowserProofDTO,
        command: ActivateInvitationCommand,
        context: IdempotencyContextDTO,
    ) -> InvitationActivationResultDTO:
        if (
            context.method != HttpMethod.POST
            or context.requested_route != "/v1/invitations/activate"
        ):
            raise RuntimeError("Activation changed its original method or route.")
        digest = command.token.digest()
        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._invitation_assignment_facts_reader.lock_for_activation(
                    identity=proof.identity, digest=digest
                )
                if facts is None:
                    raise ResourceNotFoundError()
                invitation, state = facts.invitation, facts.credential_state
                if state.identity != proof.identity or not invitation.digest.matches(digest):
                    raise RuntimeError(
                        "Activation facts changed the verified identity or invitation."
                    )
                if not HumanAdmissionPolicy.may_admit(
                    principal=facts.principal,
                    organization_id=invitation.organization_id,
                    has_pending_recovery=state.has_pending_recovery,
                ):
                    raise ConflictError("The activation recipient is not currently admissible.")
                if state.version is None and facts.has_credential_history:
                    raise DependencyUnavailableError()
                fingerprint = self._invitation_fingerprint_service.for_activation(
                    command, invitation_id=invitation.invitation_id
                )
                original = (
                    await self._invitation_activation_operation_store.read_activation_original(
                        installation_id=state.installation_id,
                        identity=proof.identity,
                        organization_id=invitation.organization_id,
                        invitation_id=invitation.invitation_id,
                        principal_id=facts.principal.id if facts.principal is not None else None,
                        context=context,
                        fingerprint=fingerprint,
                    )
                )
                if original is not None:
                    if (
                        facts.principal is None
                        or original.principal_id != facts.principal.id
                        or original.invitation_id != invitation.invitation_id
                        or original.organization_id != invitation.organization_id
                    ):
                        raise RuntimeError(
                            "The activation original changed its recipient or scope."
                        )
                    if (
                        original.operation.created is not False
                        or original.operation.replay_kind is not OperationReplayKind.SAFE_RESULT
                        or original.operation.expires_at.utcoffset() is None
                        or original.operation.expires_at <= facts.current_time
                    ):
                        raise ConflictError("The activation has no coherent live original outcome.")
                    RevisionValidation.require(original.organization_access_revision)
                    for project in original.project_access_revisions:
                        RevisionValidation.require(project.access_revision)
                    return original
                if not InvitationPolicy.may_consume(
                    expires_at=invitation.expires_at,
                    current_time=facts.current_time,
                    revoked_at=invitation.revoked_at,
                    consumed_at=invitation.consumed_at,
                ):
                    raise ResourceNotFoundError()
                if proof.password_completed is None:
                    raise DependencyUnavailableError()
                if proof.password_completed is not True:
                    raise ConflictError("Password setup is required before fresh activation.")
                issuer = await self._invitation_assignment_facts_reader.read_current_issuer(
                    invitation=invitation
                )
                if issuer is None or not issuer.has_coherent_identity:
                    raise ConflictError("The invitation issuer is not currently eligible.")
                actor = issuer.organization_access
                if (
                    actor.principal.id != invitation.issuer_principal_id
                    or actor.principal.organization_id != invitation.organization_id
                    or actor.access_revision != facts.organization_access_revision
                    or tuple(item.intent for item in issuer.assignments) != invitation.assignments
                ):
                    raise RuntimeError(
                        "Activation observations changed the retained issuer or intent."
                    )
                # No issuer credential is being presented. Coherence and recovery are
                # current account observations, independent of Alice's issuance login.
                eligibility = PrincipalAccessPolicyInput(
                    principal=actor.principal,
                    has_pending_recovery=actor.has_pending_recovery,
                    credential_is_current=True,
                )
                if not HumanAdmissionPolicy.may_authorize(
                    eligibility,
                    has_admit_users=any(
                        grant.action_id.value == OrganizationAction.ADMIT_USERS.value
                        for grant in actor.grants
                    ),
                ):
                    raise ConflictError(
                        "The invitation issuer no longer holds admission authority."
                    )
                if not all(item.target_exists for item in issuer.assignments):
                    raise ConflictError("An intended invitation target is no longer available.")
                prepared = await self._invitation_assignment_service.prepare(
                    facts=facts, issuer=issuer
                )
                RevisionValidation.require(facts.organization_access_revision)
                if (
                    facts.principal is None
                    and facts.organization_access_revision == RevisionValidation.MAX_VALUE
                ):
                    raise ConflictError("The Organization Access revision cannot advance.")
                binding = await self._invitation_activation_operation_store.reserve_activation(
                    installation_id=state.installation_id,
                    identity=proof.identity,
                    invitation=invitation,
                    principal_id=facts.principal.id if facts.principal is not None else None,
                    context=context,
                    fingerprint=fingerprint,
                )
                principal = facts.principal or Principal(
                    id=PrincipalId(uuid4()),
                    organization_id=invitation.organization_id,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.ACTIVE,
                )
                revision = await self._invitation_admission_writer.apply_invitation_admission(
                    binding=binding, facts=facts, issuer=issuer, principal=principal
                )
                bound = await self._invitation_activation_operation_store.bind_activation_principal(
                    binding=binding, principal=principal
                )
                revision, project_revisions = await self._invitation_assignment_service.apply(
                    binding=bound,
                    principal=principal,
                    states=prepared,
                    organization_access_revision=revision,
                )
                return await self._invitation_activation_operation_store.complete_activation(
                    binding=bound,
                    digest=digest,
                    organization_access_revision=revision,
                    project_access_revisions=project_revisions,
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None
