"""Validate the whole promise before writes and retain native assignment ownership."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest

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
from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
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
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
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
from inframeld_backend.access.application.services.invitation_assignment_service import (
    InvitationAssignmentService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policy_inputs.organization_grant_candidate_policy_input import (
    OrganizationGrantCandidatePolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ORG = OrganizationId(UUID(int=1))
PROJECT = ProjectId(UUID(int=2))
GROUP = AccessGroupId(UUID(int=3))
APP = PrincipalId(UUID(int=4))
ALICE = Principal(
    id=PrincipalId(UUID(int=5)),
    organization_id=ORG,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
BOB = replace(ALICE, id=PrincipalId(UUID(int=6)))
INSTALLATION = InstallationId(UUID(int=7))
IDENTITY = VerifiedHumanIdentityDTO(
    authority=IdentityAuthority("kratos:test"), subject=IdentitySubject(str(UUID(int=8)))
)
ACTOR = ProjectActionFactsDTO(
    principal=ALICE,
    has_pending_recovery=False,
    oauth_credential_facts=None,
    project_status=ProjectStatus.ACTIVE,
    is_project_member=True,
    has_exact_action_grant=True,
)
ORG_INTENT = InvitationActionGrantIntentDTO(
    target=OrganizationGrantTargetDTO(organization_id=ORG),
    action_id=ActionId("create-projects"),
    can_grant=False,
)
GROUP_GRANT = InvitationActionGrantIntentDTO(
    target=AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=GROUP),
    action_id=ActionId("add-documents"),
    can_grant=True,
)
PROJECT_GRANT = InvitationActionGrantIntentDTO(
    target=ProjectGrantTargetDTO(project_id=PROJECT),
    action_id=ActionId("create-access-groups"),
    can_grant=False,
)
MANAGER = InvitationGroupManagerIntentDTO(project_id=PROJECT, access_group_id=GROUP)
APP_GRANT = InvitationActionGrantIntentDTO(
    target=ApplicationAccountGrantTargetDTO(project_id=PROJECT, application_principal_id=APP),
    action_id=ActionId("issue-application-keys"),
    can_grant=True,
)
MEMBER = InvitationGroupMembershipIntentDTO(project_id=PROJECT, access_group_id=GROUP)
PROJECT_MEMBER = InvitationProjectMembershipIntentDTO(project_id=PROJECT)
INTENTS = (ORG_INTENT, GROUP_GRANT, PROJECT_GRANT, MANAGER, APP_GRANT, MEMBER, PROJECT_MEMBER)
NOW = datetime.now(UTC)
RECORD = InvitationRecordDTO(
    invitation_id=InvitationId(UUID(int=9)),
    organization_id=ORG,
    issuer_principal_id=ALICE.id,
    digest=InvitationToken("A" * 43).digest(),
    assignments=INTENTS,
    issued_operation_id=OperationId("issued"),
    issued_access_revision=4,
    issued_at=NOW,
    expires_at=NOW + timedelta(days=7),
)
ACTIVATION = InvitationActivationFactsDTO(
    invitation=RECORD,
    principal=BOB,
    credential_state=HumanCredentialStateDTO(
        installation_id=INSTALLATION,
        identity=IDENTITY,
        version=HumanCredentialVersion(1),
        has_pending_recovery=False,
    ),
    has_credential_history=False,
    current_time=NOW,
    organization_access_revision=5,
)
ISSUER = InvitationIssuerFactsDTO(
    organization_access=OrganizationAccessFactsDTO(
        principal=ALICE,
        access_revision=5,
        grants=(
            OrganizationActionGrantDTO(action_id=ActionId("admit-users"), can_grant=True),
            OrganizationActionGrantDTO(action_id=ORG_INTENT.action_id, can_grant=True),
        ),
        has_pending_recovery=False,
        oauth_credential_facts=None,
    ),
    has_coherent_identity=True,
    assignments=tuple(
        InvitationAssignmentFactsDTO(
            intent=intent,
            project=None
            if intent is ORG_INTENT
            else ProjectMembershipObservationDTO(
                installation_id=INSTALLATION,
                organization_id=ORG,
                project_id=PROJECT,
                access_revision=10,
                action=ACTOR,
            ),
            target_exists=True,
            actor_can_grant=True,
            actor_is_group_member=True,
            actor_is_group_manager=True,
        )
        for intent in INTENTS
    ),
)
BINDING = InvitationActivationBindingDTO(
    operation_id=OperationId("activation"),
    installation_id=INSTALLATION,
    identity=IDENTITY,
    organization_id=ORG,
    invitation_id=RECORD.invitation_id,
    issuer_principal_id=ALICE.id,
    principal_id=BOB.id,
    context=IdempotencyContextDTO(
        method=HttpMethod.POST,
        requested_route="/v1/invitations/activate",
        key=IdempotencyKey("original"),
    ),
    fingerprint=RequestFingerprint(b"F" * 32),
)


def _states() -> tuple[InvitationAssignmentStateDTO, ...]:
    return (
        InvitationAssignmentStateDTO(
            intent=ORG_INTENT,
            facts=OrganizationGrantManagementFactsDTO(
                installation_id=INSTALLATION,
                organization_id=ORG,
                action_id=ORG_INTENT.action_id,
                access_revision=5,
                actor=ALICE,
                actor_can_grant=True,
                actor_has_pending_recovery=False,
                actor_oauth_credential_facts=None,
                recipient=BOB,
                recipient_has_pending_recovery=False,
                recipient_has_coherent_identity=True,
                assignment=ActionGrantState(None),
                other_grantors=(),
            ),
        ),
        InvitationAssignmentStateDTO(
            intent=GROUP_GRANT,
            facts=AccessGroupGrantManagementFactsDTO(
                installation_id=INSTALLATION,
                organization_id=ORG,
                project_id=PROJECT,
                group_id=GROUP,
                action_id=GROUP_GRANT.action_id,
                access_revision=10,
                actor=ACTOR,
                actor_can_grant=True,
                actor_is_group_member=True,
                actor_is_group_manager=True,
                recipient=BOB,
                recipient_is_project_member=False,
                recipient_has_pending_recovery=False,
                recipient_has_coherent_identity=True,
                recipient_application_is_bound=False,
                assignment=ActionGrantState(None),
                grantors=(),
            ),
        ),
        InvitationAssignmentStateDTO(
            intent=PROJECT_GRANT,
            facts=ProjectActionGrantManagementFactsDTO(
                installation_id=INSTALLATION,
                organization_id=ORG,
                project_id=PROJECT,
                action_id=PROJECT_GRANT.action_id,
                grant=ProjectGrantChangeFactsDTO(
                    actor=ALICE,
                    has_pending_recovery=False,
                    oauth_credential_facts=None,
                    recipient=BOB,
                    project_status=ProjectStatus.ACTIVE,
                    project_access_revision=10,
                    actor_is_project_member=True,
                    recipient_is_project_member=False,
                    actor_can_grant_action=True,
                ),
                recipient_has_pending_recovery=False,
                recipient_has_coherent_identity=True,
                recipient_application_is_project_bound=False,
                other_grantors=(),
            ),
        ),
        InvitationAssignmentStateDTO(
            intent=MANAGER,
            facts=AccessGroupChangeFactsDTO(
                organization_id=ORG,
                project_id=PROJECT,
                access_revision=10,
                group_id=GROUP,
                action=ACTOR,
                recipient=BOB,
                recipient_is_project_member=False,
                recipient_has_coherent_identity=True,
                recipient_has_pending_recovery=False,
                relationships=AccessGroupRelationships(member=False, manager=False),
            ),
        ),
        InvitationAssignmentStateDTO(
            intent=APP_GRANT,
            facts=ApplicationAccountGrantManagementFactsDTO(
                installation_id=INSTALLATION,
                organization_id=ORG,
                project_id=PROJECT,
                application_principal_id=APP,
                action_id=APP_GRANT.action_id,
                access_revision=10,
                actor=ACTOR,
                actor_can_grant=True,
                recipient=BOB,
                recipient_is_project_member=False,
                recipient_has_pending_recovery=False,
                recipient_has_coherent_identity=True,
                assignment=ActionGrantState(None),
                grantors=(),
            ),
        ),
        InvitationAssignmentStateDTO(
            intent=MEMBER,
            facts=AccessGroupChangeFactsDTO(
                organization_id=ORG,
                project_id=PROJECT,
                access_revision=10,
                group_id=GROUP,
                action=ACTOR,
                recipient=BOB,
                recipient_is_project_member=False,
                recipient_has_coherent_identity=True,
                recipient_has_pending_recovery=False,
                relationships=AccessGroupRelationships(member=False, manager=False),
            ),
        ),
        InvitationAssignmentStateDTO(
            intent=PROJECT_MEMBER,
            facts=ProjectMembershipChangeFactsDTO(
                installation_id=INSTALLATION,
                organization_id=ORG,
                project_id=PROJECT,
                access_revision=10,
                action=ACTOR,
                recipient=BOB,
                recipient_has_pending_recovery=False,
                recipient_has_coherent_identity=True,
                recipient_is_project_member=False,
            ),
        ),
    )


class _Facts(InvitationAssignmentFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.states: tuple[InvitationAssignmentStateDTO, ...] | None = _states()
        states = _states()
        self.current: dict[InvitationAssignmentDTO, InvitationAssignmentStateDTO] = {
            PROJECT_MEMBER: states[6],
            MEMBER: replace(
                states[5],
                facts=replace(
                    _group(states[5]), access_revision=11, recipient_is_project_member=True
                ),
            ),
            MANAGER: replace(
                states[3],
                facts=replace(
                    _group(states[3]),
                    access_revision=12,
                    recipient_is_project_member=True,
                    relationships=AccessGroupRelationships(member=True, manager=False),
                ),
            ),
            ORG_INTENT: states[0],
            GROUP_GRANT: replace(
                states[1],
                facts=replace(
                    _group_grant(states[1]), access_revision=13, recipient_is_project_member=True
                ),
            ),
            PROJECT_GRANT: replace(
                states[2],
                facts=replace(
                    _project_grant(states[2]),
                    grant=replace(
                        _project_grant(states[2]).grant,
                        project_access_revision=14,
                        recipient_is_project_member=True,
                    ),
                ),
            ),
            APP_GRANT: replace(
                states[4],
                facts=replace(
                    _app_grant(states[4]), access_revision=15, recipient_is_project_member=True
                ),
            ),
        }

    @override
    async def lock_for_activation(
        self, *, identity: VerifiedHumanIdentityDTO, digest: InvitationTokenDigest
    ) -> InvitationActivationFactsDTO | None:
        raise AssertionError("Assignment orchestration does not own identity coordination.")

    @override
    async def read_current_issuer(
        self, *, invitation: InvitationRecordDTO
    ) -> InvitationIssuerFactsDTO | None:
        raise AssertionError("The activation caller supplies current retained issuer facts.")

    @override
    async def read_assignment_states(
        self, *, invitation: InvitationRecordDTO, recipient: Principal | None
    ) -> tuple[InvitationAssignmentStateDTO, ...] | None:
        self.events.append("preflight")
        return self.states

    @override
    async def read_assignment_state(
        self, *, invitation_id: InvitationId, recipient: Principal, intent: InvitationAssignmentDTO
    ) -> InvitationAssignmentStateDTO | None:
        assert invitation_id == RECORD.invitation_id and recipient.id == BOB.id
        self.events.append("refresh")
        return self.current.get(intent)


def _group(state: InvitationAssignmentStateDTO) -> AccessGroupChangeFactsDTO:
    assert isinstance(state.facts, AccessGroupChangeFactsDTO)
    return state.facts


def _group_grant(state: InvitationAssignmentStateDTO) -> AccessGroupGrantManagementFactsDTO:
    assert isinstance(state.facts, AccessGroupGrantManagementFactsDTO)
    return state.facts


def _project_grant(state: InvitationAssignmentStateDTO) -> ProjectActionGrantManagementFactsDTO:
    assert isinstance(state.facts, ProjectActionGrantManagementFactsDTO)
    return state.facts


def _app_grant(state: InvitationAssignmentStateDTO) -> ApplicationAccountGrantManagementFactsDTO:
    assert isinstance(state.facts, ApplicationAccountGrantManagementFactsDTO)
    return state.facts


class _Membership(InvitationProjectMembershipWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def apply_invitation_membership(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: ProjectMembershipChangeFactsDTO,
        principal_id: PrincipalId,
    ) -> int:
        assert binding == BINDING and principal_id == BOB.id
        self.events.append("project-member")
        return facts.access_revision + int(not facts.recipient_is_project_member)


class _Groups(InvitationGroupRelationshipWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def apply_invitation_relationship(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        after: AccessGroupRelationships,
    ) -> int:
        assert (
            binding == BINDING
            and command.principal_id == BOB.id
            and command.expected_access_revision == facts.access_revision
        )
        self.events.append("group-manager" if after.manager else "group-member")
        return facts.access_revision + int(after != facts.relationships)


class _Organization(InvitationOrganizationGrantWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def apply_invitation_grant(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: OrganizationGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        after: ActionGrantState,
    ) -> int:
        assert (
            binding == BINDING
            and recipient_principal_id == BOB.id
            and type(after.can_grant) is bool
        )
        self.events.append("organization-grant")
        return facts.access_revision + int(after != facts.assignment)


class _GroupGrants(InvitationAccessGroupGrantWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def apply_invitation_grant(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: AccessGroupGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        after: ActionGrantState,
    ) -> int:
        assert binding == BINDING and recipient_principal_id == BOB.id
        self.events.append("group-grant")
        return facts.access_revision + int(after != facts.assignment)


class _ApplicationGrants(InvitationApplicationGrantWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def apply_invitation_grant(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: ApplicationAccountGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        after: ActionGrantState,
    ) -> int:
        assert binding == BINDING and recipient_principal_id == BOB.id
        self.events.append("application-grant")
        return facts.access_revision + int(after != facts.assignment)


class _Repository(ProjectMembershipRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.membership = ProjectMembership(
            organization_id=ORG,
            project_id=PROJECT,
            principal_id=BOB.id,
            principal_kind=PrincipalKind.HUMAN,
            grants=(),
        )
        self.saved: list[tuple[ActionId, PrincipalId, int, OperationId]] = []

    @override
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId, principal_id: PrincipalId
    ) -> ProjectMembership:
        assert (
            organization_id == self.membership.organization_id
            and project_id == self.membership.project_id
            and principal_id == self.membership.principal_id
        )
        self.events.append("repository-get")
        return self.membership

    @override
    async def save_action_grant_change(
        self,
        membership: ProjectMembership,
        *,
        action_id: ActionId,
        actor_principal_id: PrincipalId,
        expected_project_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        assert membership is self.membership
        self.events.append("project-grant")
        self.saved.append(
            (action_id, actor_principal_id, expected_project_access_revision, operation_id)
        )

    @override
    async def save(
        self,
        membership: ProjectMembership,
        *,
        expected_project_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        raise AssertionError("Invitation exact SET must use save_action_grant_change.")


def _scenario() -> tuple[InvitationAssignmentService, _Facts, _Repository, list[str]]:
    events: list[str] = []
    facts, repository = _Facts(events), _Repository(events)
    return (
        InvitationAssignmentService(
            invitation_assignment_facts_reader=facts,
            invitation_project_membership_writer=_Membership(events),
            invitation_group_relationship_writer=_Groups(events),
            invitation_organization_grant_writer=_Organization(events),
            invitation_access_group_grant_writer=_GroupGrants(events),
            invitation_application_grant_writer=_ApplicationGrants(events),
            project_membership_repository=repository,
        ),
        facts,
        repository,
        events,
    )


@pytest.mark.asyncio
async def test_preflight_validates_all_seven_real_forms_without_applying_effects() -> None:
    service, facts, _, events = _scenario()
    prepared = await service.prepare(facts=ACTIVATION, issuer=ISSUER)
    assert prepared == facts.states
    assert events == ["preflight"]


@pytest.mark.asyncio
async def test_effects_refresh_actual_prerequisites_before_seven_native_owners() -> None:
    service, _, repository, events = _scenario()
    result = await service.apply(
        binding=BINDING, principal=BOB, states=_states(), organization_access_revision=5
    )
    assert result == (
        6,
        (InvitationProjectAccessRevisionDTO(project_id=PROJECT, access_revision=16),),
    )
    assert [v for v in events if v not in {"refresh", "repository-get"}] == [
        "project-member",
        "group-member",
        "group-manager",
        "organization-grant",
        "group-grant",
        "project-grant",
        "application-grant",
    ]
    assert repository.saved == [(PROJECT_GRANT.action_id, ALICE.id, 14, BINDING.operation_id)]
    grant = repository.membership.grants[0]
    assert grant.level is ProjectGrantLevel.USE_ONLY and grant.assigned_by_principal_id == ALICE.id


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [PROJECT_MEMBER, MEMBER])
async def test_only_explicit_project_membership_can_supply_that_prerequisite(
    missing: InvitationAssignmentDTO,
) -> None:
    service, facts, _, events = _scenario()
    intents = tuple(v for v in INTENTS if v != missing)
    issuer = replace(
        ISSUER, assignments=tuple(v for v in ISSUER.assignments if v.intent != missing)
    )
    assert facts.states is not None
    facts.states = tuple(v for v in facts.states if v.intent != missing)
    activation = replace(ACTIVATION, invitation=replace(RECORD, assignments=intents))
    if missing == PROJECT_MEMBER:
        with pytest.raises(ConflictError):
            await service.prepare(facts=activation, issuer=issuer)
    else:
        assert await service.prepare(facts=activation, issuer=issuer) == facts.states
    assert not any(v in events for v in ["project-member", "group-member", "group-manager"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed", ["pairing", "reduced", "order", "organization", "action", "issuer", "recipient"]
)
async def test_preflight_rejects_native_fact_pairing_or_exact_binding_changes(
    malformed: str,
) -> None:
    service, facts, _, events = _scenario()
    states = list(_states())
    org = states[0].facts
    assert isinstance(org, OrganizationGrantManagementFactsDTO)
    if malformed == "pairing":
        states[0] = replace(states[0], facts=states[1].facts)
    elif malformed == "reduced":
        states.pop()
    elif malformed == "order":
        states.reverse()
    elif malformed == "organization":
        states[0] = replace(
            states[0], facts=replace(org, organization_id=OrganizationId(UUID(int=99)))
        )
    elif malformed == "action":
        states[0] = replace(states[0], facts=replace(org, action_id=ActionId("admit-users")))
    elif malformed == "issuer":
        states[0] = replace(states[0], facts=replace(org, actor=BOB))
    else:
        states[0] = replace(states[0], facts=replace(org, recipient=ALICE))
    facts.states = tuple(states)
    with pytest.raises(RuntimeError) as caught:
        await service.prepare(facts=ACTIVATION, issuer=ISSUER)
    assert type(caught.value) is RuntimeError
    assert not any(v.endswith("grant") or v.endswith("member") for v in events)


@pytest.mark.asyncio
async def test_refreshed_prerequisites_are_not_repaired_from_the_promised_intent() -> None:
    service, facts, _, events = _scenario()
    member = facts.current[MEMBER]
    facts.current[MEMBER] = replace(
        member, facts=replace(_group(member), recipient_is_project_member=False)
    )
    with pytest.raises(ConflictError):
        await service.apply(
            binding=BINDING, principal=BOB, states=_states(), organization_access_revision=5
        )
    assert "project-member" in events and "group-member" not in events


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["organization", "group", "project", "application"])
@pytest.mark.parametrize(
    ("before_level", "desired"), [(False, False), (True, True), (False, True), (True, False)]
)
async def test_exact_native_set_accepts_equal_upgrade_and_downgrade_levels(
    target: str, before_level: bool, desired: bool
) -> None:
    service, reader, repository, _ = _scenario()
    index = {"organization": 0, "group": 1, "project": 2, "application": 4}[target]
    state = _states()[index]
    assert isinstance(state.intent, InvitationActionGrantIntentDTO)
    intent = replace(state.intent, can_grant=desired)
    candidate = ProjectDepartureCandidatePolicyInput(
        principal=ALICE,
        has_pending_recovery=False,
        is_project_member=True,
        has_coherent_identity=True,
        can_grant=True,
        is_group_member=True,
        is_group_manager=True,
    )
    native = state.facts
    if isinstance(native, OrganizationGrantManagementFactsDTO):
        native = replace(
            native,
            assignment=ActionGrantState(before_level),
            other_grantors=(
                OrganizationGrantCandidatePolicyInput(
                    principal=ALICE,
                    has_pending_recovery=False,
                    has_coherent_identity=True,
                    can_grant=True,
                ),
            ),
        )
    elif isinstance(native, ProjectActionGrantManagementFactsDTO):
        native = replace(
            native,
            grant=replace(native.grant, recipient_is_project_member=True),
            other_grantors=(candidate,),
        )
        repository.membership = ProjectMembership(
            organization_id=ORG,
            project_id=PROJECT,
            principal_id=BOB.id,
            principal_kind=PrincipalKind.HUMAN,
            grants=(
                ProjectActionGrant(
                    project_id=PROJECT,
                    recipient_principal_id=BOB.id,
                    action_id=intent.action_id,
                    level=ProjectGrantLevel.USE_AND_GRANT
                    if before_level
                    else ProjectGrantLevel.USE_ONLY,
                    assigned_by_principal_id=PrincipalId(UUID(int=77)),
                ),
            ),
        )
    elif isinstance(native, AccessGroupGrantManagementFactsDTO):
        native = replace(
            native,
            recipient_is_project_member=True,
            assignment=ActionGrantState(before_level),
            grantors=(candidate,),
        )
    else:
        assert isinstance(native, ApplicationAccountGrantManagementFactsDTO)
        native = replace(
            native,
            recipient_is_project_member=True,
            assignment=ActionGrantState(before_level),
            grantors=(candidate,),
        )
    state = replace(state, intent=intent, facts=native)
    reader.states = (state,)
    reader.current = {intent: state}
    activation = replace(
        ACTIVATION,
        invitation=replace(RECORD, assignments=(intent,)),
        project_memberships=frozenset({PROJECT}),
    )
    observed = next(item for item in ISSUER.assignments if item.intent == _states()[index].intent)
    issuer = replace(ISSUER, assignments=(replace(observed, intent=intent),))
    prepared = await service.prepare(facts=activation, issuer=issuer)
    org, projects = await service.apply(
        binding=BINDING, principal=BOB, states=prepared, organization_access_revision=5
    )
    changed = before_level is not desired
    assert org == (5 + int(changed) if target == "organization" else 5)
    assert projects == (
        ()
        if target == "organization"
        else (
            InvitationProjectAccessRevisionDTO(
                project_id=PROJECT, access_revision=10 + int(changed)
            ),
        )
    )
    if target == "project":
        grant = repository.membership.grants[0]
        assert grant.assigned_by_principal_id == PrincipalId(UUID(int=77))
        assert grant.level is (
            ProjectGrantLevel.USE_AND_GRANT if desired else ProjectGrantLevel.USE_ONLY
        )


@pytest.mark.asyncio
async def test_absent_recipient_preflight_keeps_actual_absence_until_admission() -> None:
    service, reader, _, events = _scenario()
    states: list[InvitationAssignmentStateDTO] = []
    for state in _states():
        native = state.facts
        if isinstance(native, ProjectActionGrantManagementFactsDTO):
            native = replace(
                native,
                grant=replace(native.grant, recipient=None),
                recipient_has_coherent_identity=False,
            )
        else:
            native = replace(native, recipient=None, recipient_has_coherent_identity=False)
        states.append(replace(state, facts=native))
    reader.states = tuple(states)
    facts = replace(
        ACTIVATION,
        principal=None,
        credential_state=replace(ACTIVATION.credential_state, version=None),
    )
    assert await service.prepare(facts=facts, issuer=ISSUER) == tuple(states)
    assert events == ["preflight"]
    assert all(state.facts.recipient_has_coherent_identity is False for state in states)


@pytest.mark.asyncio
async def test_known_revision_exhaustion_is_rejected_before_any_mutation() -> None:
    service, reader, _, events = _scenario()
    state = _states()[-1]
    assert isinstance(state.facts, ProjectMembershipChangeFactsDTO)
    state = replace(state, facts=replace(state.facts, access_revision=2**53 - 1))
    reader.states = (state,)
    observed = ISSUER.assignments[-1]
    assert observed.project is not None
    issuer = replace(
        ISSUER,
        assignments=(
            replace(observed, project=replace(observed.project, access_revision=2**53 - 1)),
        ),
    )
    activation = replace(ACTIVATION, invitation=replace(RECORD, assignments=(PROJECT_MEMBER,)))
    with pytest.raises(ConflictError):
        await service.prepare(facts=activation, issuer=issuer)
    assert events == ["preflight"]


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["organization", "project", "application"])
async def test_self_downgrade_cannot_remove_last_eligible_native_delegator(target: str) -> None:
    service, reader, repository, events = _scenario()
    state = _states()[{"organization": 0, "project": 2, "application": 4}[target]]
    assert isinstance(state.intent, InvitationActionGrantIntentDTO)
    intent = replace(state.intent, can_grant=False)
    candidate = ProjectDepartureCandidatePolicyInput(
        principal=ALICE,
        has_pending_recovery=False,
        is_project_member=True,
        has_coherent_identity=True,
        can_grant=True,
        is_group_member=False,
        is_group_manager=False,
    )
    native = state.facts
    if isinstance(native, OrganizationGrantManagementFactsDTO):
        native = replace(
            native,
            recipient=ALICE,
            assignment=ActionGrantState(True),
            other_grantors=(
                OrganizationGrantCandidatePolicyInput(
                    principal=ALICE,
                    has_pending_recovery=False,
                    has_coherent_identity=True,
                    can_grant=True,
                ),
            ),
        )
    elif isinstance(native, ProjectActionGrantManagementFactsDTO):
        native = replace(
            native,
            grant=replace(native.grant, recipient=ALICE, recipient_is_project_member=True),
            other_grantors=(candidate,),
        )
        repository.membership = ProjectMembership(
            organization_id=ORG,
            project_id=PROJECT,
            principal_id=ALICE.id,
            principal_kind=PrincipalKind.HUMAN,
            grants=(
                ProjectActionGrant(
                    project_id=PROJECT,
                    recipient_principal_id=ALICE.id,
                    action_id=intent.action_id,
                    level=ProjectGrantLevel.USE_AND_GRANT,
                    assigned_by_principal_id=ALICE.id,
                ),
            ),
        )
    else:
        assert isinstance(native, ApplicationAccountGrantManagementFactsDTO)
        native = replace(
            native,
            recipient=ALICE,
            recipient_is_project_member=True,
            assignment=ActionGrantState(True),
            grantors=(candidate,),
        )
    reader.states = (replace(state, intent=intent, facts=native),)
    observed = next(item for item in ISSUER.assignments if item.intent == state.intent)
    issuer = replace(ISSUER, assignments=(replace(observed, intent=intent),))
    activation = replace(
        ACTIVATION,
        principal=ALICE,
        invitation=replace(RECORD, assignments=(intent,)),
        project_memberships=frozenset({PROJECT}),
    )
    with pytest.raises(ConflictError):
        await service.prepare(facts=activation, issuer=issuer)
    assert not any(v.endswith("grant") for v in events)


@pytest.mark.asyncio
@pytest.mark.parametrize("manager", [False, True])
async def test_group_handover_keeps_the_same_humans_unchanged_management(manager: bool) -> None:
    service, reader, _, events = _scenario()
    state = _states()[1]
    native = _group_grant(state)
    intent = replace(GROUP_GRANT, can_grant=False)
    candidate = ProjectDepartureCandidatePolicyInput(
        principal=ALICE,
        has_pending_recovery=False,
        is_project_member=True,
        has_coherent_identity=True,
        can_grant=True,
        is_group_member=True,
        is_group_manager=manager,
    )
    native = replace(
        native,
        recipient=ALICE,
        recipient_is_project_member=True,
        actor_is_group_manager=manager,
        assignment=ActionGrantState(True),
        grantors=(candidate,),
    )
    reader.states = (replace(state, intent=intent, facts=native),)
    observed = replace(ISSUER.assignments[1], intent=intent, actor_is_group_manager=manager)
    activation = replace(
        ACTIVATION,
        principal=ALICE,
        invitation=replace(RECORD, assignments=(intent,)),
        project_memberships=frozenset({PROJECT}),
    )
    issuer = replace(ISSUER, assignments=(observed,))
    if manager:
        assert await service.prepare(facts=activation, issuer=issuer) == reader.states
    else:
        with pytest.raises(ConflictError):
            await service.prepare(facts=activation, issuer=issuer)
    assert events == ["preflight"]
