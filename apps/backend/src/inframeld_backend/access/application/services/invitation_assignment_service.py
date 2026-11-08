from dataclasses import replace

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_management_facts_dto import (
    AccessGroupGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_facts_dto import (
    InvitationActivationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_facts_dto import (
    InvitationAssignmentFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_state_dto import (
    InvitationAssignmentStateDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_issuer_facts_dto import (
    InvitationIssuerFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.protocols.invitation_access_group_grant_writer import (
    InvitationAccessGroupGrantWriter,
)
from inframeld_backend.access.application.protocols.invitation_application_grant_writer import (
    InvitationApplicationGrantWriter,
)
from inframeld_backend.access.application.protocols.invitation_assignment_facts_reader import (
    InvitationAssignmentFactsReader,
)
from inframeld_backend.access.application.protocols.invitation_group_relationship_writer import (
    InvitationGroupRelationshipWriter,
)
from inframeld_backend.access.application.protocols.invitation_organization_grant_writer import (
    InvitationOrganizationGrantWriter,
)
from inframeld_backend.access.application.protocols.invitation_project_membership_writer import (
    InvitationProjectMembershipWriter,
)
from inframeld_backend.access.application.protocols.project_membership_repository import (
    ProjectMembershipRepository,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.policies.access_group_grant_policy import (
    AccessGroupGrantPolicy,
)
from inframeld_backend.access.domain.policies.access_group_relationship_policy import (
    AccessGroupRelationshipPolicy,
)
from inframeld_backend.access.domain.policies.action_authorization_policy import (
    ActionAuthorizationPolicy,
)
from inframeld_backend.access.domain.policies.application_account_grant_policy import (
    ApplicationAccountGrantPolicy,
)
from inframeld_backend.access.domain.policies.organization_grant_policy import (
    OrganizationGrantPolicy,
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
from inframeld_backend.access.domain.policy_inputs.action_authorization_policy_input import (
    ActionAuthorizationPolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_responsibility_policy_input import (
    ProjectDepartureResponsibilityPolicyInput,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class InvitationAssignmentService:
    """Validate the whole Access promise and apply exact effects in the activation caller's turn.

    This component owns neither a transaction nor provider work. Preserve native
    domain policies, checked persistence owners and the direct Project aggregate.
    """

    def __init__(
        self,
        *,
        invitation_assignment_facts_reader: InvitationAssignmentFactsReader,
        invitation_project_membership_writer: InvitationProjectMembershipWriter,
        invitation_group_relationship_writer: InvitationGroupRelationshipWriter,
        invitation_organization_grant_writer: InvitationOrganizationGrantWriter,
        invitation_access_group_grant_writer: InvitationAccessGroupGrantWriter,
        invitation_application_grant_writer: InvitationApplicationGrantWriter,
        project_membership_repository: ProjectMembershipRepository,
    ) -> None:
        self._invitation_assignment_facts_reader = invitation_assignment_facts_reader
        self._invitation_project_membership_writer = invitation_project_membership_writer
        self._invitation_group_relationship_writer = invitation_group_relationship_writer
        self._invitation_organization_grant_writer = invitation_organization_grant_writer
        self._invitation_access_group_grant_writer = invitation_access_group_grant_writer
        self._invitation_application_grant_writer = invitation_application_grant_writer
        self._project_membership_repository = project_membership_repository

    async def prepare(
        self, *, facts: InvitationActivationFactsDTO, issuer: InvitationIssuerFactsDTO
    ) -> tuple[InvitationAssignmentStateDTO, ...]:
        """Validate all current authority, exact targets and explicit prospective prerequisites before writes."""
        assignments = facts.invitation.assignments
        if len(assignments) == 1 and isinstance(assignments[0], InvitationAdmissionOnlyIntentDTO):
            return ()
        if tuple(item.intent for item in issuer.assignments) != assignments:
            raise RuntimeError("Assignment authority observations changed the complete intent.")
        for observation in issuer.assignments:
            self._require_authority(issuer, observation)
        states = await self._invitation_assignment_facts_reader.read_assignment_states(
            invitation=facts.invitation, recipient=facts.principal
        )
        if states is None:
            raise ConflictError("An intended assignment target is no longer available.")
        if tuple(item.intent for item in states) != assignments:
            raise RuntimeError("Assignment observations changed or reduced the complete intent.")
        promised_memberships = {
            item.project_id
            for item in assignments
            if isinstance(item, InvitationProjectMembershipIntentDTO)
        }
        for state in states:
            self._require_pairing(
                state,
                organization_id=facts.invitation.organization_id,
                issuer_id=facts.invitation.issuer_principal_id,
                installation_id=facts.credential_state.installation_id,
                recipient=facts.principal,
            )
            project = self._project_id(state.intent)
            if (
                project is not None
                and not isinstance(state.intent, InvitationProjectMembershipIntentDTO)
                and project not in facts.project_memberships
                and project not in promised_memberships
            ):
                raise ConflictError(
                    "The invitation requires an explicit Project-membership prerequisite."
                )
            if facts.principal is not None:
                self._require_recipient_account(state)
            if isinstance(state.intent, InvitationActionGrantIntentDTO):
                await self._require_handover(state, facts.principal)
        await self._require_revision_room(facts, states)
        return states

    async def apply(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        principal: Principal,
        states: tuple[InvitationAssignmentStateDTO, ...],
        organization_access_revision: int,
    ) -> tuple[int, tuple[InvitationProjectAccessRevisionDTO, ...]]:
        """Refresh real facts after flushed prerequisites and apply each native transition once.

        New assignments attribute the issuer, replacements retain native assignment
        attribution, and unchanged transitions preserve counters and timestamps.
        Return the exact final Organization and affected Project revisions.
        """
        projects: dict[ProjectId, int] = {}
        ordered = self._ordered(states)
        if len(ordered) != len(states):
            raise RuntimeError("Assignment execution received an unsupported intent.")
        for original in ordered:
            state = await self._invitation_assignment_facts_reader.read_assignment_state(
                invitation_id=binding.invitation_id, recipient=principal, intent=original.intent
            )
            if state is None:
                raise ConflictError("An intended assignment target is no longer available.")
            if state.intent != original.intent:
                raise RuntimeError("Assignment refresh changed its exact requested intent.")
            self._require_pairing(
                state,
                organization_id=binding.organization_id,
                issuer_id=binding.issuer_principal_id,
                installation_id=binding.installation_id,
                recipient=principal,
            )
            self._require_current_recipient(state)
            before = self._revision(state)
            project = self._project_id(state.intent)
            if project is None:
                if before != organization_access_revision:
                    raise RuntimeError(
                        "Assignment refresh changed the current Organization revision."
                    )
            elif project in projects and projects[project] != before:
                raise RuntimeError(
                    "Assignment refresh did not observe the preceding flushed transition."
                )
            intent, native = state.intent, state.facts
            if isinstance(intent, InvitationProjectMembershipIntentDTO):
                if not isinstance(native, ProjectMembershipChangeFactsDTO):
                    raise RuntimeError("Project membership changed its native facts.")
                changed = not native.recipient_is_project_member
                after = (
                    await self._invitation_project_membership_writer.apply_invitation_membership(
                        binding=binding, facts=native, principal_id=principal.id
                    )
                )
            elif isinstance(
                intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
            ):
                if not isinstance(native, AccessGroupChangeFactsDTO):
                    raise RuntimeError("Group relationship changed its native facts.")
                managing = isinstance(intent, InvitationGroupManagerIntentDTO)
                relationships = (
                    AccessGroupRelationshipPolicy.appoint_manager(native.relationships)
                    if managing
                    else AccessGroupRelationshipPolicy.add_member(native.relationships)
                )
                changed = relationships != native.relationships
                after = (
                    await self._invitation_group_relationship_writer.apply_invitation_relationship(
                        binding=binding,
                        facts=native,
                        command=ChangeAccessGroupRelationshipCommand(
                            project_id=intent.project_id,
                            group_id=intent.access_group_id,
                            principal_id=principal.id,
                            expected_access_revision=before,
                            change_kind=AccessGroupChangeKind.APPOINT_MANAGER
                            if managing
                            else AccessGroupChangeKind.ADD_MEMBER,
                        ),
                        after=relationships,
                    )
                )
            elif isinstance(intent, InvitationActionGrantIntentDTO):
                if isinstance(native, OrganizationGrantManagementFactsDTO):
                    assignment = native.assignment.set_level(can_grant=intent.can_grant)
                    changed = assignment != native.assignment
                    after = await self._invitation_organization_grant_writer.apply_invitation_grant(
                        binding=binding,
                        facts=native,
                        recipient_principal_id=principal.id,
                        after=assignment,
                    )
                elif isinstance(native, AccessGroupGrantManagementFactsDTO):
                    assignment = native.assignment.set_level(can_grant=intent.can_grant)
                    changed = assignment != native.assignment
                    after = await self._invitation_access_group_grant_writer.apply_invitation_grant(
                        binding=binding,
                        facts=native,
                        recipient_principal_id=principal.id,
                        after=assignment,
                    )
                elif isinstance(native, ApplicationAccountGrantManagementFactsDTO):
                    assignment = native.assignment.set_level(can_grant=intent.can_grant)
                    changed = assignment != native.assignment
                    after = await self._invitation_application_grant_writer.apply_invitation_grant(
                        binding=binding,
                        facts=native,
                        recipient_principal_id=principal.id,
                        after=assignment,
                    )
                elif isinstance(native, ProjectActionGrantManagementFactsDTO):
                    membership = await self._membership(state, principal)
                    changed = membership.set_action_grant(
                        action_id=intent.action_id,
                        level=ProjectGrantLevel.USE_AND_GRANT
                        if intent.can_grant
                        else ProjectGrantLevel.USE_ONLY,
                        assigned_by_principal_id=binding.issuer_principal_id,
                    )
                    await self._project_membership_repository.save_action_grant_change(
                        membership,
                        action_id=intent.action_id,
                        actor_principal_id=binding.issuer_principal_id,
                        expected_project_access_revision=before,
                        operation_id=binding.operation_id,
                    )
                    after = before + int(changed)
                else:
                    raise RuntimeError("Action grant changed its native owner.")
            else:
                raise RuntimeError("Assignment execution received an unsupported intent.")
            RevisionValidation.require(after)
            if after != before + int(changed):
                raise RuntimeError("The native assignment changed its exact transition revision.")
            if project is None:
                organization_access_revision = after
            else:
                projects[project] = after
        return organization_access_revision, tuple(
            InvitationProjectAccessRevisionDTO(project_id=project, access_revision=revision)
            for project, revision in sorted(projects.items(), key=lambda item: item[0].value.int)
        )

    @staticmethod
    def _project_id(intent: InvitationAssignmentDTO) -> ProjectId | None:
        if isinstance(
            intent,
            (
                InvitationProjectMembershipIntentDTO,
                InvitationGroupMembershipIntentDTO,
                InvitationGroupManagerIntentDTO,
            ),
        ):
            return intent.project_id
        if isinstance(intent, InvitationActionGrantIntentDTO) and isinstance(
            intent.target,
            (ProjectGrantTargetDTO, AccessGroupGrantTargetDTO, ApplicationAccountGrantTargetDTO),
        ):
            return intent.target.project_id
        return None

    @staticmethod
    def _revision(state: InvitationAssignmentStateDTO) -> int:
        revision = (
            state.facts.grant.project_access_revision
            if isinstance(state.facts, ProjectActionGrantManagementFactsDTO)
            else state.facts.access_revision
        )
        RevisionValidation.require(revision)
        return revision

    @staticmethod
    def _recipient(state: InvitationAssignmentStateDTO) -> Principal | None:
        return (
            state.facts.grant.recipient
            if isinstance(state.facts, ProjectActionGrantManagementFactsDTO)
            else state.facts.recipient
        )

    @staticmethod
    def _member(state: InvitationAssignmentStateDTO) -> bool:
        if isinstance(state.facts, OrganizationGrantManagementFactsDTO):
            return False
        return (
            state.facts.grant.recipient_is_project_member
            if isinstance(state.facts, ProjectActionGrantManagementFactsDTO)
            else state.facts.recipient_is_project_member
        )

    @staticmethod
    def _require_pairing(
        state: InvitationAssignmentStateDTO,
        *,
        organization_id: OrganizationId,
        issuer_id: PrincipalId,
        installation_id: InstallationId,
        recipient: Principal | None,
    ) -> None:
        intent, native = state.intent, state.facts
        paired = False
        if isinstance(intent, InvitationProjectMembershipIntentDTO):
            paired = isinstance(native, ProjectMembershipChangeFactsDTO)
        elif isinstance(
            intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
        ):
            paired = (
                isinstance(native, AccessGroupChangeFactsDTO)
                and native.group_id == intent.access_group_id
            )
        elif isinstance(intent, InvitationActionGrantIntentDTO):
            if isinstance(intent.target, OrganizationGrantTargetDTO):
                paired = (
                    isinstance(native, OrganizationGrantManagementFactsDTO)
                    and native.action_id == intent.action_id
                    and intent.target.organization_id == organization_id
                )
            elif isinstance(intent.target, ProjectGrantTargetDTO):
                paired = (
                    isinstance(native, ProjectActionGrantManagementFactsDTO)
                    and native.action_id == intent.action_id
                )
            elif isinstance(intent.target, AccessGroupGrantTargetDTO):
                paired = (
                    isinstance(native, AccessGroupGrantManagementFactsDTO)
                    and native.group_id == intent.target.access_group_id
                    and native.action_id == intent.action_id
                )
            elif isinstance(intent.target, ApplicationAccountGrantTargetDTO):
                paired = (
                    isinstance(native, ApplicationAccountGrantManagementFactsDTO)
                    and native.application_principal_id == intent.target.application_principal_id
                    and native.action_id == intent.action_id
                )
        if not paired or native.organization_id != organization_id:
            raise RuntimeError(
                "Assignment observations changed their closed native pairing or Organization."
            )
        project = InvitationAssignmentService._project_id(intent)
        if project is not None and (
            isinstance(native, OrganizationGrantManagementFactsDTO) or native.project_id != project
        ):
            raise RuntimeError("Assignment observations changed their exact Project.")
        if isinstance(native, (ProjectMembershipChangeFactsDTO, AccessGroupChangeFactsDTO)):
            actor = native.action.principal
        elif isinstance(native, ProjectActionGrantManagementFactsDTO):
            actor = native.grant.actor
        elif isinstance(native, OrganizationGrantManagementFactsDTO):
            actor = native.actor
        else:
            actor = native.actor.principal
        if actor.id != issuer_id or actor.organization_id != organization_id:
            raise RuntimeError("Assignment observations changed the retained issuer.")
        if (
            not isinstance(native, AccessGroupChangeFactsDTO)
            and native.installation_id != installation_id
        ):
            raise RuntimeError("Assignment observations changed the installation.")
        observed = InvitationAssignmentService._recipient(state)
        if (observed is None) != (recipient is None) or (
            observed is not None
            and recipient is not None
            and (
                observed.id != recipient.id
                or observed.organization_id != organization_id
                or observed.kind is not PrincipalKind.HUMAN
            )
        ):
            raise RuntimeError("Assignment observations changed the exact recipient.")
        InvitationAssignmentService._revision(state)

    @staticmethod
    def _require_authority(
        issuer: InvitationIssuerFactsDTO, observed: InvitationAssignmentFactsDTO
    ) -> None:
        intent = observed.intent
        actor = issuer.organization_access.principal
        # Retained issuer records are observed without presenting an issuer
        # credential, so the OAuth credential-binding check does not apply here.
        eligibility = PrincipalAccessPolicyInput(
            principal=actor,
            has_pending_recovery=issuer.organization_access.has_pending_recovery,
            credential_is_current=True,
        )
        if not observed.target_exists:
            raise ConflictError("An intended assignment target is no longer available.")
        if isinstance(intent, InvitationActionGrantIntentDTO) and isinstance(
            intent.target, OrganizationGrantTargetDTO
        ):
            if (
                intent.target.organization_id != actor.organization_id
                or not OrganizationGrantPolicy.supports_action(intent.action_id)
                or not OrganizationGrantPolicy.may_manage(
                    actor_access=eligibility,
                    can_grant_action=any(
                        grant.action_id == intent.action_id and grant.can_grant
                        for grant in issuer.organization_access.grants
                    ),
                )
            ):
                raise ConflictError(
                    "The invitation issuer no longer holds the exact Organization delegation."
                )
            return
        project = observed.project
        if project is None:
            raise ConflictError("The intended Project is no longer available.")
        if (
            project.project_id != InvitationAssignmentService._project_id(intent)
            or project.organization_id != actor.organization_id
            or project.action.principal.id != actor.id
        ):
            raise RuntimeError("Assignment authority changed its exact current Project or issuer.")
        current = PrincipalAccessPolicyInput(
            principal=project.action.principal,
            has_pending_recovery=project.action.has_pending_recovery,
            credential_is_current=True,
        )
        if not ProjectVisibilityPolicy.may_view_project(
            principal_status=current.principal.status,
            project_status=project.action.project_status,
            is_project_member=project.action.is_project_member,
        ) or not PrincipalAccessPolicy.may_use_product(current):
            raise ConflictError("The invitation issuer is not currently eligible in the Project.")
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
        elif isinstance(intent, InvitationActionGrantIntentDTO):
            if isinstance(intent.target, AccessGroupGrantTargetDTO):
                allowed = AccessGroupGrantPolicy.supports_recipient(
                    action_id=intent.action_id, kind=PrincipalKind.HUMAN, can_grant=intent.can_grant
                ) and AccessGroupGrantPolicy.may_manage(
                    actor_access=current,
                    is_project_member=project.action.is_project_member,
                    can_grant_action=observed.actor_can_grant,
                    is_group_member=observed.actor_is_group_member,
                    is_group_manager=observed.actor_is_group_manager,
                )
            elif isinstance(
                intent.target, (ProjectGrantTargetDTO, ApplicationAccountGrantTargetDTO)
            ):
                supported = (
                    ProjectActionEligibilityPolicy.may_use(
                        action_id=intent.action_id, principal_kind=PrincipalKind.HUMAN
                    )
                    if isinstance(intent.target, ProjectGrantTargetDTO)
                    else ApplicationAccountGrantPolicy.supports_recipient(
                        action_id=intent.action_id, kind=PrincipalKind.HUMAN
                    )
                )
                allowed = supported and ProjectGrantDelegationPolicy.may_delegate_project_action(
                    actor_access=current,
                    actor_is_project_member=project.action.is_project_member,
                    actor_can_grant_action=observed.actor_can_grant,
                )
            else:
                allowed = False
        else:
            allowed = False
        if not allowed:
            raise ConflictError("The invitation issuer no longer holds every promised authority.")

    @staticmethod
    def _require_recipient_account(state: InvitationAssignmentStateDTO) -> None:
        recipient = InvitationAssignmentService._recipient(state)
        if recipient is None:
            raise ConflictError("The assignment recipient is not currently admitted.")
        native = state.facts
        if (
            recipient.kind is not PrincipalKind.HUMAN
            or not native.recipient_has_coherent_identity
            or not PrincipalAccessPolicy.may_use_product(
                PrincipalAccessPolicyInput(
                    principal=recipient,
                    has_pending_recovery=native.recipient_has_pending_recovery,
                    credential_is_current=True,
                )
            )
        ):
            raise ConflictError("The assignment recipient is not currently eligible.")

    @staticmethod
    def _require_current_recipient(state: InvitationAssignmentStateDTO) -> None:
        InvitationAssignmentService._require_recipient_account(state)
        native, intent = state.facts, state.intent
        if not isinstance(
            native, (OrganizationGrantManagementFactsDTO, ProjectMembershipChangeFactsDTO)
        ) and not InvitationAssignmentService._member(state):
            raise ConflictError(
                "An intended Project-membership prerequisite is not actually present."
            )
        recipient = InvitationAssignmentService._recipient(state)
        if recipient is None:
            raise ConflictError()
        eligibility = PrincipalAccessPolicyInput(
            principal=recipient,
            has_pending_recovery=native.recipient_has_pending_recovery,
            credential_is_current=True,
        )
        if isinstance(native, OrganizationGrantManagementFactsDTO):
            allowed = OrganizationGrantPolicy.may_receive(
                recipient_access=eligibility,
                has_coherent_identity=native.recipient_has_coherent_identity,
            )
        elif isinstance(native, AccessGroupChangeFactsDTO):
            allowed = AccessGroupRelationshipPolicy.may_add_member(
                principal=recipient,
                is_project_member=native.recipient_is_project_member,
                has_coherent_identity=native.recipient_has_coherent_identity,
                has_pending_recovery=native.recipient_has_pending_recovery,
            )
        elif isinstance(native, AccessGroupGrantManagementFactsDTO):
            allowed = AccessGroupGrantPolicy.may_receive(
                recipient_access=eligibility,
                is_project_member=native.recipient_is_project_member,
                has_coherent_identity=native.recipient_has_coherent_identity,
                application_is_bound=native.recipient_application_is_bound,
            )
        elif isinstance(native, ApplicationAccountGrantManagementFactsDTO):
            allowed = ApplicationAccountGrantPolicy.may_receive(
                recipient_access=eligibility,
                is_project_member=native.recipient_is_project_member,
                has_coherent_identity=native.recipient_has_coherent_identity,
            )
        elif isinstance(native, ProjectActionGrantManagementFactsDTO) and isinstance(
            intent, InvitationActionGrantIntentDTO
        ):
            allowed = ProjectGrantDelegationPolicy.may_assign_to_recipient(
                recipient_access=eligibility,
                is_project_member=native.grant.recipient_is_project_member,
                has_coherent_identity=native.recipient_has_coherent_identity,
                application_is_project_bound=native.recipient_application_is_project_bound,
                action_id=intent.action_id,
                can_grant=intent.can_grant,
            )
        else:
            allowed = True
        if not allowed:
            raise ConflictError(
                "The assignment recipient does not meet the native eligibility policy."
            )

    async def _membership(
        self, state: InvitationAssignmentStateDTO, principal: Principal
    ) -> ProjectMembership:
        project = self._project_id(state.intent)
        if project is None:
            raise RuntimeError("The exact Project grant has no Project scope.")
        membership = await self._project_membership_repository.get(
            organization_id=principal.organization_id, project_id=project, principal_id=principal.id
        )
        if (
            membership.organization_id != principal.organization_id
            or membership.project_id != project
            or membership.principal_id != principal.id
            or membership.principal_kind is not PrincipalKind.HUMAN
        ):
            raise RuntimeError("The exact Project aggregate changed its checked membership scope.")
        return membership

    async def _require_handover(
        self, state: InvitationAssignmentStateDTO, recipient: Principal | None
    ) -> None:
        intent, native = state.intent, state.facts
        if not isinstance(intent, InvitationActionGrantIntentDTO):
            return
        if isinstance(native, ProjectActionGrantManagementFactsDTO):
            before: bool | None = None
            if recipient is not None and native.grant.recipient_is_project_member:
                membership = await self._membership(state, recipient)
                grant = next(
                    (item for item in membership.grants if item.action_id == intent.action_id), None
                )
                if grant is not None:
                    before = grant.level is ProjectGrantLevel.USE_AND_GRANT
        elif isinstance(
            native,
            (
                OrganizationGrantManagementFactsDTO,
                AccessGroupGrantManagementFactsDTO,
                ApplicationAccountGrantManagementFactsDTO,
            ),
        ):
            before = native.assignment.can_grant
        else:
            raise RuntimeError("The exact grant changed its native handover owner.")
        if before is not True or intent.can_grant:
            return
        if recipient is None:
            raise RuntimeError("An absent recipient cannot own an existing delegation.")
        if isinstance(native, OrganizationGrantManagementFactsDTO):
            if any(
                item.principal.organization_id != native.organization_id
                for item in native.other_grantors
            ):
                raise RuntimeError("Organization handover returned a foreign candidate.")
            allowed = OrganizationGrantPolicy.has_remaining_grantor(
                tuple(item for item in native.other_grantors if item.principal.id != recipient.id)
            )
        else:
            candidates = (
                native.other_grantors
                if isinstance(native, ProjectActionGrantManagementFactsDTO)
                else native.grantors
            )
            if any(item.principal.organization_id != native.organization_id for item in candidates):
                raise RuntimeError("Target handover returned a foreign candidate.")
            remaining = (
                tuple(item for item in candidates if item.principal.id != recipient.id)
                if isinstance(native, ProjectActionGrantManagementFactsDTO)
                else tuple(
                    replace(item, can_grant=False) if item.principal.id == recipient.id else item
                    for item in candidates
                )
            )
            target = (
                ProjectDepartureTargetKind.PROJECT
                if isinstance(native, ProjectActionGrantManagementFactsDTO)
                else (
                    ProjectDepartureTargetKind.ACCESS_GROUP
                    if isinstance(native, AccessGroupGrantManagementFactsDTO)
                    else ProjectDepartureTargetKind.APPLICATION_ACCOUNT
                )
            )
            allowed = ProjectDeparturePolicy.may_depart(
                (
                    ProjectDepartureResponsibilityPolicyInput(
                        target_kind=target, action_id=intent.action_id, candidates=remaining
                    ),
                )
            )
        if not allowed:
            raise ConflictError("The target must retain an eligible human exact-action grantor.")

    @staticmethod
    def _ordered(
        states: tuple[InvitationAssignmentStateDTO, ...],
    ) -> tuple[InvitationAssignmentStateDTO, ...]:
        return (
            tuple(
                item
                for item in states
                if isinstance(item.intent, InvitationProjectMembershipIntentDTO)
            )
            + tuple(
                item
                for item in states
                if isinstance(item.intent, InvitationGroupMembershipIntentDTO)
            )
            + tuple(
                item for item in states if isinstance(item.intent, InvitationGroupManagerIntentDTO)
            )
            + tuple(
                item for item in states if isinstance(item.intent, InvitationActionGrantIntentDTO)
            )
        )

    async def _require_revision_room(
        self, facts: InvitationActivationFactsDTO, states: tuple[InvitationAssignmentStateDTO, ...]
    ) -> None:
        """Reject known exhaustion for the complete promised transitions before the first write."""
        organization_changes = int(facts.principal is None)
        changes: dict[ProjectId, int] = {}
        revisions: dict[ProjectId, int] = {}
        relationships: dict[tuple[ProjectId, AccessGroupId], AccessGroupRelationships] = {}
        for state in self._ordered(states):
            native, intent = state.facts, state.intent
            project = self._project_id(intent)
            revision = self._revision(state)
            if project is not None:
                if revisions.setdefault(project, revision) != revision:
                    raise RuntimeError(
                        "Assignment observations disagree on a current Project revision."
                    )
            elif revision != facts.organization_access_revision:
                raise RuntimeError(
                    "Assignment observations disagree on the current Organization revision."
                )
            if isinstance(native, ProjectMembershipChangeFactsDTO):
                changed = not native.recipient_is_project_member
            elif isinstance(native, AccessGroupChangeFactsDTO) and isinstance(
                intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
            ):
                key = (native.project_id, native.group_id)
                before = relationships.get(key, native.relationships)
                after = (
                    AccessGroupRelationshipPolicy.appoint_manager(before)
                    if isinstance(intent, InvitationGroupManagerIntentDTO)
                    else AccessGroupRelationshipPolicy.add_member(before)
                )
                relationships[key] = after
                changed = before != after
            elif isinstance(native, ProjectActionGrantManagementFactsDTO) and isinstance(
                intent, InvitationActionGrantIntentDTO
            ):
                previous: bool | None = None
                if facts.principal is not None and native.grant.recipient_is_project_member:
                    membership = await self._membership(state, facts.principal)
                    grant = next(
                        (item for item in membership.grants if item.action_id == intent.action_id),
                        None,
                    )
                    if grant is not None:
                        previous = grant.level is ProjectGrantLevel.USE_AND_GRANT
                changed = previous is not intent.can_grant
            elif isinstance(
                native,
                (
                    OrganizationGrantManagementFactsDTO,
                    AccessGroupGrantManagementFactsDTO,
                    ApplicationAccountGrantManagementFactsDTO,
                ),
            ) and isinstance(intent, InvitationActionGrantIntentDTO):
                changed = native.assignment.can_grant is not intent.can_grant
            else:
                raise RuntimeError("Assignment changed its native transition owner.")
            if project is None:
                organization_changes += int(changed)
            else:
                changes[project] = changes.get(project, 0) + int(changed)
        if (
            facts.organization_access_revision + organization_changes > RevisionValidation.MAX_VALUE
            or any(
                revisions[project] + count > RevisionValidation.MAX_VALUE
                for project, count in changes.items()
            )
        ):
            raise ConflictError(
                "The complete invitation exceeds remaining Access revision capacity."
            )
