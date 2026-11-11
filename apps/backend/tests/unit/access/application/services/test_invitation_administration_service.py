"""Authorize the complete promise before safe issuance replay and fresh effects."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from unittest.mock import patch
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import MockTransactions

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
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
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
from inframeld_backend.access.application.dtos.invitation_facts_dto import InvitationFactsDTO
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_pipeline_target_dto import (
    InvitationPipelineTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
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
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.application.protocols.invitation_facts_reader import (
    InvitationFactsReader,
)
from inframeld_backend.access.application.protocols.invitation_writer import InvitationWriter
from inframeld_backend.access.application.services.invitation_administration_service import (
    InvitationAdministrationService,
)
from inframeld_backend.access.application.services.invitation_fingerprint_service import (
    InvitationFingerprintService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
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
    AuthenticationRequiredError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ORG = OrganizationId(UUID(int=1))
PROJECT = ProjectId(UUID(int=2))
GROUP = AccessGroupId(UUID(int=3))
ALICE = Principal(
    id=PrincipalId(UUID(int=4)),
    organization_id=ORG,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
IDENTITY = VerifiedHumanIdentityDTO(
    authority=IdentityAuthority("kratos:test"), subject=IdentitySubject(str(UUID(int=5)))
)
ACCESS = AccessContextDTO(
    actor_principal_id=ALICE.id,
    authentication_evidence=MockAuthenticationEvidence.browser(IDENTITY),
)
ADMISSION = InvitationAdmissionOnlyIntentDTO()
COMMAND = IssueInvitationCommand(
    organization_id=ORG,
    assignments=(ADMISSION,),
    expected_access_revision=7,
    expected_project_access_revisions=(),
)
CONTEXT = IdempotencyContextDTO(
    method=HttpMethod.POST,
    requested_route="/v1/invitations",
    key=IdempotencyKey("original-invitation"),
)
TOKEN = InvitationToken("A" * 43)
NOW = datetime(2026, 11, 7, tzinfo=UTC)
OPERATION = OperationId("issue-invitation-original")
COMPLETED = CompletedSynchronousOperationDTO(
    operation_id=OPERATION,
    created=True,
    replay_kind=OperationReplayKind.ISSUED_SECRET,
    expires_at=NOW + timedelta(days=1),
)
ACTOR = OrganizationAccessFactsDTO(
    principal=ALICE,
    access_revision=7,
    grants=(OrganizationActionGrantDTO(action_id=ActionId("admit-users"), can_grant=True),),
    has_pending_recovery=False,
    oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
)
ASSIGNMENT = InvitationAssignmentFactsDTO(
    intent=ADMISSION,
    project=None,
    target_exists=True,
    actor_can_grant=False,
    actor_is_group_member=False,
    actor_is_group_manager=False,
)
FACTS = InvitationFactsDTO(organization_id=ORG, actor=ACTOR, assignments=(ASSIGNMENT,))
ORIGINAL = InvitationRecordDTO(
    invitation_id=InvitationId(UUID(int=8)),
    organization_id=ORG,
    issuer_principal_id=ALICE.id,
    digest=TOKEN.digest(),
    assignments=(ADMISSION,),
    issued_operation_id=OPERATION,
    issued_access_revision=8,
    issued_at=NOW,
    expires_at=NOW + timedelta(days=7),
)


class _Facts(InvitationFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.value: InvitationFactsDTO | None = FACTS
        self.original: InvitationRecordDTO | None = ORIGINAL
        self.revocation: InvitationRevocationFactsDTO | None = InvitationRevocationFactsDTO(
            organization_id=ORG, actor=ACTOR, invitation=ORIGINAL
        )
        self.revocation_original: InvitationRevocationResultDTO | None = None

    @override
    async def read_by_digest(self, digest: InvitationTokenDigest) -> InvitationRecordDTO | None:
        raise AssertionError("Issuance must not inspect a recipient token.")

    @override
    async def lock_for_issue(
        self, *, access: AccessContextDTO, command: IssueInvitationCommand
    ) -> InvitationFactsDTO | None:
        self.events.append("facts")
        return self.value

    @override
    async def read_issue_original(
        self,
        *,
        organization_id: OrganizationId,
        issuer_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> InvitationRecordDTO | None:
        self.events.append("original")
        return self.original

    @override
    async def lock_for_revocation(
        self, *, access: AccessContextDTO, invitation_id: InvitationId
    ) -> InvitationRevocationFactsDTO | None:
        self.events.append("revoke_facts")
        return self.revocation

    @override
    async def read_revocation_original(
        self,
        *,
        organization_id: OrganizationId,
        actor_principal_id: PrincipalId,
        invitation_id: InvitationId,
        operation_id: OperationId,
    ) -> InvitationRevocationResultDTO | None:
        self.events.append("revoke_original")
        return self.revocation_original


class _Writer(InvitationWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.saved: InvitationRecordDTO | None = None
        self.error: Exception | None = None
        self.revoked: (
            tuple[InvitationRecordDTO, InvitationRevocationResultDTO, PrincipalId, int, datetime]
            | None
        ) = None

    @override
    async def save_issue(
        self, *, record: InvitationRecordDTO, expected_access_revision: int
    ) -> None:
        self.events.append("save")
        if self.error is not None:
            raise self.error
        self.saved = record
        assert expected_access_revision == 7

    @override
    async def save_revocation(
        self,
        *,
        invitation: InvitationRecordDTO,
        result: InvitationRevocationResultDTO,
        actor_principal_id: PrincipalId,
        expected_access_revision: int,
        revoked_at: datetime,
    ) -> None:
        self.events.append("revoke_save")
        if self.error is not None:
            raise self.error
        self.revoked = (
            invitation,
            result,
            actor_principal_id,
            expected_access_revision,
            revoked_at,
        )


class _Idempotency(OperationIdempotency):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: NewOperationReservationDTO | CompletedSynchronousOperationDTO = (
            NewOperationReservationDTO(OPERATION)
        )
        self.completed = COMPLETED
        self.fingerprint: RequestFingerprint | None = None
        self.expected_kind: OperationReplayKind | None = None

    @override
    async def reserve_or_recover[ProjectScope: ProjectId | None](
        self,
        *,
        context: IdempotencyContextDTO,
        access: AccessContextDTO,
        authorization: AuthorizedOperationScope[ProjectScope],
        fingerprint: RequestFingerprint,
        expected_replay_kind: OperationReplayKind,
        lookup_authority: OperationLookupAuthority | None = None,
    ) -> NewOperationReservationDTO | CompletedSynchronousOperationDTO:
        self.events.append("reserve")
        self.fingerprint = fingerprint
        self.expected_kind = expected_replay_kind
        return self.result

    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> CompletedSynchronousOperationDTO:
        self.events.append("complete")
        assert replay_kind is self.expected_kind
        return self.completed


class _Scenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.facts = _Facts(self.events)
        self.writer = _Writer(self.events)
        self.idempotency = _Idempotency(self.events)
        self.transactions = MockTransactions(self.events)
        self.fingerprints = InvitationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
        )
        self.service = InvitationAdministrationService(
            transaction_manager=self.transactions,
            invitation_facts_reader=self.facts,
            invitation_writer=self.writer,
            operation_idempotency=self.idempotency,
            invitation_fingerprint_service=self.fingerprints,
            default_lifetime_seconds=7 * 86400,
            maximum_lifetime_seconds=30 * 86400,
        )


@pytest.mark.asyncio
async def test_first_delivery_saves_only_digest_then_returns_one_secret() -> None:
    s = _Scenario()
    with patch.object(InvitationToken, "generate", return_value=TOKEN) as generate:
        result = await s.service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert s.events == ["begin", "facts", "reserve", "save", "complete", "commit"]
    assert s.writer.saved is not None and s.writer.saved.digest.matches(TOKEN.digest())
    assert result.token is TOKEN and result.invitation_id == s.writer.saved.invitation_id
    assert (
        result.access_revision == 8
        and result.expires_at == s.writer.saved.issued_at + timedelta(days=7)
    )
    assert s.idempotency.expected_kind is OperationReplayKind.ISSUED_SECRET
    generate.assert_called_once()


@pytest.mark.asyncio
async def test_replay_keeps_original_expiry_revision_and_never_mints_a_secret() -> None:
    s = _Scenario()
    s.idempotency.result = replace(COMPLETED, created=False)
    s.facts.value = replace(FACTS, actor=replace(ACTOR, access_revision=90))
    s.facts.original = replace(
        ORIGINAL, issued_at=NOW - timedelta(days=8), expires_at=NOW - timedelta(days=1)
    )
    with patch.object(InvitationToken, "generate") as generate:
        result = await s.service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.token is None and result.access_revision == 8
    assert (
        result.expires_at == NOW - timedelta(days=1)
        and result.operation.expires_at == COMPLETED.expires_at
    )
    assert s.writer.saved is None and s.events == [
        "begin",
        "facts",
        "reserve",
        "original",
        "commit",
    ]
    generate.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial", ["missing", "grant", "recovery", "suspended", "application", "actor", "foreign"]
)
async def test_current_authority_precedes_original_history(denial: str) -> None:
    s = _Scenario()
    s.idempotency.result = replace(COMPLETED, created=False)
    actor = ACTOR
    access = ACCESS
    expected: type[Exception] = AccessDeniedError
    if denial == "missing":
        s.facts.value = None
        expected = ResourceNotFoundError
    elif denial == "grant":
        actor = replace(ACTOR, grants=())
    elif denial == "recovery":
        actor = replace(ACTOR, has_pending_recovery=True)
    elif denial == "suspended":
        actor = replace(ACTOR, principal=replace(ALICE, status=PrincipalStatus.SUSPENDED))
    elif denial == "application":
        actor = replace(ACTOR, principal=replace(ALICE, kind=PrincipalKind.APPLICATION))
        access = replace(
            ACCESS,
            authentication_evidence=ApplicationKeyAuthenticationDTO(
                key_id=ApplicationKeyId(UUID(int=30))
            ),
        )
    elif denial == "actor":
        actor = replace(ACTOR, principal=replace(ALICE, id=PrincipalId(UUID(int=99))))
        expected = RuntimeError
    else:
        actor = replace(
            ACTOR, principal=replace(ALICE, organization_id=OrganizationId(UUID(int=99)))
        )
        expected = ResourceNotFoundError
    if denial != "missing":
        s.facts.value = replace(FACTS, actor=actor)
    with pytest.raises(expected) as caught:
        await s.service.issue(access=access, command=COMMAND, context=CONTEXT)
    assert type(caught.value) is expected
    assert "reserve" not in s.events and "original" not in s.events and s.writer.saved is None


@pytest.mark.asyncio
async def test_stale_oauth_generation_prevents_history_disclosure() -> None:
    s = _Scenario()
    access = replace(ACCESS, authentication_evidence=MockAuthenticationEvidence.human_oauth())
    s.facts.value = replace(
        FACTS,
        actor=replace(
            ACTOR,
            oauth_credential_facts=HumanCredentialFactsDTO(
                binding_matches_actor=True, current_version=HumanCredentialVersion(2)
            ),
        ),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await s.service.issue(access=access, command=COMMAND, context=CONTEXT)
    assert "reserve" not in s.events


@pytest.mark.asyncio
async def test_fresh_revision_is_checked_after_reservation_and_before_effects() -> None:
    s = _Scenario()
    s.facts.value = replace(FACTS, actor=replace(ACTOR, access_revision=9))
    with pytest.raises(StaleRevisionError):
        await s.service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert s.events == ["begin", "facts", "reserve", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        replace(CONTEXT, method=HttpMethod.PUT),
        replace(CONTEXT, requested_route="/v1/invitations/preview"),
    ],
)
async def test_route_identity_cannot_be_reinterpreted(context: IdempotencyContextDTO) -> None:
    s = _Scenario()
    with pytest.raises(RuntimeError) as caught:
        await s.service.issue(access=ACCESS, command=COMMAND, context=context)
    assert type(caught.value) is RuntimeError
    assert s.events == []


@pytest.mark.asyncio
async def test_missing_original_is_unavailable_and_never_reissued() -> None:
    s = _Scenario()
    s.idempotency.result = replace(COMPLETED, created=False)
    s.facts.original = None
    with (
        patch.object(InvitationToken, "generate") as generate,
        pytest.raises(DependencyUnavailableError),
    ):
        await s.service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    generate.assert_not_called()
    assert s.writer.saved is None


@pytest.mark.asyncio
async def test_writer_failure_prevents_completion_and_commits_no_mock_transaction() -> None:
    s = _Scenario()
    s.writer.error = ConflictError()
    with pytest.raises(ConflictError):
        await s.service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert "complete" not in s.events and s.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_wrong_completion_kind_is_not_treated_as_a_secret_delivery() -> None:
    s = _Scenario()
    s.idempotency.completed = replace(COMPLETED, replay_kind=OperationReplayKind.SAFE_RESULT)
    with pytest.raises(ConflictError):
        await s.service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert s.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("seconds", [1, 30 * 86400])
async def test_requested_lifetime_is_exact_within_configured_bound(seconds: int) -> None:
    s = _Scenario()
    result = await s.service.issue(
        access=ACCESS, command=replace(COMMAND, expires_in_seconds=seconds), context=CONTEXT
    )
    assert s.writer.saved is not None and result.expires_at == s.writer.saved.issued_at + timedelta(
        seconds=seconds
    )


@pytest.mark.asyncio
async def test_fresh_lifetime_above_configuration_applies_no_effects() -> None:
    s = _Scenario()
    with pytest.raises(InvalidInputError):
        await s.service.issue(
            access=ACCESS,
            command=replace(COMMAND, expires_in_seconds=30 * 86400 + 1),
            context=CONTEXT,
        )
    assert s.writer.saved is None and "complete" not in s.events


def test_fingerprint_binds_intent_revision_and_requested_lifetime() -> None:
    s = _Scenario()
    original = s.fingerprints.for_issue(COMMAND)
    assert original != s.fingerprints.for_issue(replace(COMMAND, expected_access_revision=8))
    assert original != s.fingerprints.for_issue(replace(COMMAND, expires_in_seconds=1))
    grant = InvitationActionGrantIntentDTO(
        target=OrganizationGrantTargetDTO(organization_id=ORG),
        action_id=ActionId("create-projects"),
        can_grant=False,
    )
    assert original != s.fingerprints.for_issue(replace(COMMAND, assignments=(grant,)))


def _project_observation(
    *, member: bool = True, has_action: bool = True
) -> ProjectMembershipObservationDTO:
    return ProjectMembershipObservationDTO(
        installation_id=InstallationId(UUID(int=20)),
        organization_id=ORG,
        project_id=PROJECT,
        access_revision=11,
        action=ProjectActionFactsDTO(
            principal=ALICE,
            has_pending_recovery=False,
            oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
            project_status=ProjectStatus.ACTIVE,
            is_project_member=member,
            has_exact_action_grant=has_action,
        ),
    )


def _with_intent(
    s: _Scenario,
    intent: InvitationAssignmentDTO,
    *,
    project: bool,
    delegation: bool = True,
    manager: bool = False,
) -> IssueInvitationCommand:
    observation = _project_observation() if project else None
    s.facts.value = replace(
        FACTS,
        assignments=(
            InvitationAssignmentFactsDTO(
                intent=intent,
                project=observation,
                target_exists=True,
                actor_can_grant=delegation,
                actor_is_group_member=manager,
                actor_is_group_manager=manager,
            ),
        ),
    )
    return replace(
        COMMAND,
        assignments=(intent,),
        expected_project_access_revisions=(
            InvitationProjectAccessRevisionDTO(project_id=PROJECT, access_revision=11),
        )
        if project
        else (),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "project-membership",
        "group-manager",
        "project-grant",
        "group-grant",
        "account-grant",
        "organization-grant",
    ],
)
async def test_complete_current_assignment_authority_allows_exact_intent(kind: str) -> None:
    s = _Scenario()
    intent: InvitationAssignmentDTO
    if kind == "project-membership":
        intent = InvitationProjectMembershipIntentDTO(project_id=PROJECT)
    elif kind == "group-manager":
        intent = InvitationGroupManagerIntentDTO(project_id=PROJECT, access_group_id=GROUP)
    elif kind == "project-grant":
        intent = InvitationActionGrantIntentDTO(
            target=ProjectGrantTargetDTO(project_id=PROJECT),
            action_id=ActionId("create-access-groups"),
            can_grant=True,
        )
    elif kind == "group-grant":
        intent = InvitationActionGrantIntentDTO(
            target=AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=GROUP),
            action_id=ActionId("add-documents"),
            can_grant=True,
        )
    elif kind == "account-grant":
        intent = InvitationActionGrantIntentDTO(
            target=ApplicationAccountGrantTargetDTO(
                project_id=PROJECT, application_principal_id=PrincipalId(UUID(int=25))
            ),
            action_id=ActionId("issue-application-keys"),
            can_grant=True,
        )
    else:
        intent = InvitationActionGrantIntentDTO(
            target=OrganizationGrantTargetDTO(organization_id=ORG),
            action_id=ActionId("create-projects"),
            can_grant=True,
        )
    command = _with_intent(
        s, intent, project=kind != "organization-grant", manager=kind == "group-manager"
    )
    if kind == "organization-grant":
        assert s.facts.value is not None
        s.facts.value = replace(
            s.facts.value,
            actor=replace(
                ACTOR,
                grants=(
                    *ACTOR.grants,
                    OrganizationActionGrantDTO(
                        action_id=ActionId("create-projects"), can_grant=True
                    ),
                ),
            ),
        )
    result = await s.service.issue(access=ACCESS, command=command, context=CONTEXT)
    assert result.assignments == (intent,) and s.writer.saved is not None
    assert s.writer.saved.assignments == (intent,)


@pytest.mark.asyncio
async def test_group_manager_document_delegation_alternative_stays_scoped() -> None:
    s = _Scenario()
    intent = InvitationActionGrantIntentDTO(
        target=AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=GROUP),
        action_id=ActionId("add-documents"),
        can_grant=True,
    )
    command = _with_intent(s, intent, project=True, delegation=False, manager=True)
    result = await s.service.issue(access=ACCESS, command=command, context=CONTEXT)
    assert result.assignments == (intent,)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "denial",
    ["project-membership", "project-deleting", "delegation", "group-half-manager", "target"],
)
async def test_assignment_denial_prevents_original_disclosure(denial: str) -> None:
    s = _Scenario()
    s.idempotency.result = replace(COMPLETED, created=False)
    intent = InvitationActionGrantIntentDTO(
        target=AccessGroupGrantTargetDTO(project_id=PROJECT, access_group_id=GROUP),
        action_id=ActionId("add-documents"),
        can_grant=False,
    )
    command = _with_intent(s, intent, project=True, delegation=False)
    assert s.facts.value is not None
    observed = s.facts.value.assignments[0]
    assert observed.project is not None
    if denial == "project-membership":
        observed = replace(
            observed,
            project=replace(
                observed.project, action=replace(observed.project.action, is_project_member=False)
            ),
        )
    elif denial == "project-deleting":
        observed = replace(
            observed,
            project=replace(
                observed.project,
                action=replace(observed.project.action, project_status=ProjectStatus.DELETING),
            ),
        )
    elif denial == "group-half-manager":
        observed = replace(observed, actor_is_group_manager=True)
    elif denial == "target":
        observed = replace(observed, target_exists=False)
    s.facts.value = replace(s.facts.value, assignments=(observed,))
    with pytest.raises(
        ResourceNotFoundError
        if denial in {"project-membership", "project-deleting", "target"}
        else AccessDeniedError
    ):
        await s.service.issue(access=ACCESS, command=command, context=CONTEXT)
    assert "reserve" not in s.events and "original" not in s.events


@pytest.mark.asyncio
async def test_group_management_does_not_delegate_application_administration() -> None:
    s = _Scenario()
    intent = InvitationActionGrantIntentDTO(
        target=ApplicationAccountGrantTargetDTO(
            project_id=PROJECT, application_principal_id=PrincipalId(UUID(int=25))
        ),
        action_id=ActionId("issue-application-keys"),
        can_grant=False,
    )
    command = _with_intent(s, intent, project=True, delegation=False, manager=True)
    with pytest.raises(AccessDeniedError):
        await s.service.issue(access=ACCESS, command=command, context=CONTEXT)
    assert "reserve" not in s.events


@pytest.mark.asyncio
async def test_future_typed_handoff_does_not_simulate_an_available_owner() -> None:
    s = _Scenario()
    intent = InvitationActionGrantIntentDTO(
        target=InvitationPipelineTargetDTO(pipeline_id=UUID(int=77)),
        action_id=ActionId("query"),
        can_grant=False,
    )
    command = _with_intent(s, intent, project=False)
    with pytest.raises(ConflictError):
        await s.service.issue(access=ACCESS, command=command, context=CONTEXT)
    assert "reserve" not in s.events and s.writer.saved is None


@pytest.mark.asyncio
async def test_incomplete_fact_set_cannot_silently_reduce_the_invitation() -> None:
    s = _Scenario()
    s.facts.value = replace(FACTS, assignments=())
    with pytest.raises(RuntimeError) as caught:
        await s.service.issue(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert type(caught.value) is RuntimeError
    assert "reserve" not in s.events


@pytest.mark.asyncio
async def test_fresh_project_revision_is_checked_before_writing() -> None:
    s = _Scenario()
    intent = InvitationProjectMembershipIntentDTO(project_id=PROJECT)
    command = _with_intent(s, intent, project=True)
    command = replace(
        command,
        expected_project_access_revisions=(
            InvitationProjectAccessRevisionDTO(project_id=PROJECT, access_revision=10),
        ),
    )
    with pytest.raises(StaleRevisionError):
        await s.service.issue(access=ACCESS, command=command, context=CONTEXT)
    assert "reserve" in s.events and s.writer.saved is None


REVOKE_COMMAND = RevokeInvitationCommand(
    invitation_id=ORIGINAL.invitation_id, expected_access_revision=7
)
REVOKE_CONTEXT = IdempotencyContextDTO(
    method=HttpMethod.POST,
    requested_route=f"/v1/invitations/{ORIGINAL.invitation_id.value}/revoke",
    key=IdempotencyKey("revoke-original"),
)
REVOKE_COMPLETED = CompletedSynchronousOperationDTO(
    operation_id=OperationId("revoke-original"),
    created=True,
    replay_kind=OperationReplayKind.SAFE_RESULT,
    expires_at=NOW + timedelta(days=1),
)


def _revocation_scenario() -> _Scenario:
    s = _Scenario()
    s.idempotency.result = NewOperationReservationDTO(REVOKE_COMPLETED.operation_id)
    s.idempotency.completed = REVOKE_COMPLETED
    return s


@pytest.mark.asyncio
async def test_revocation_saves_one_org_change_and_safe_original_without_assignment_checks() -> (
    None
):
    s = _revocation_scenario()
    assert s.facts.revocation is not None
    s.facts.revocation = replace(
        s.facts.revocation,
        invitation=replace(
            ORIGINAL, assignments=(InvitationProjectMembershipIntentDTO(project_id=PROJECT),)
        ),
    )
    result = await s.service.revoke(access=ACCESS, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
    assert s.events == ["begin", "revoke_facts", "reserve", "complete", "revoke_save", "commit"]
    assert result == InvitationRevocationResultDTO(
        invitation_id=ORIGINAL.invitation_id,
        organization_id=ORG,
        access_revision=8,
        operation=REVOKE_COMPLETED,
    )
    assert s.writer.revoked is not None
    invitation, saved, actor, revision, revoked_at = s.writer.revoked
    assert invitation is s.facts.revocation.invitation and saved == result
    assert actor == ALICE.id and revision == 7 and revoked_at.utcoffset() is not None
    assert s.idempotency.expected_kind is OperationReplayKind.SAFE_RESULT


@pytest.mark.asyncio
async def test_revocation_original_precedes_fresh_revision_and_lifecycle_checks() -> None:
    s = _revocation_scenario()
    original = InvitationRevocationResultDTO(
        invitation_id=ORIGINAL.invitation_id,
        organization_id=ORG,
        access_revision=8,
        operation=replace(REVOKE_COMPLETED, created=False),
    )
    s.idempotency.result = original.operation
    s.facts.revocation_original = original
    assert s.facts.revocation is not None
    s.facts.revocation = replace(
        s.facts.revocation,
        actor=replace(ACTOR, access_revision=99),
        invitation=replace(
            ORIGINAL, revoked_at=NOW, consumed_at=NOW, consumed_by_principal_id=ALICE.id
        ),
    )
    result = await s.service.revoke(access=ACCESS, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
    assert result == original and s.writer.revoked is None
    assert s.events == ["begin", "revoke_facts", "reserve", "revoke_original", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "is_issuer,can_grant,allowed", [(True, False, True), (False, True, True), (False, False, False)]
)
async def test_revocation_uses_issuer_or_admission_delegator_only(
    is_issuer: bool, can_grant: bool, allowed: bool
) -> None:
    s = _revocation_scenario()
    assert s.facts.revocation is not None
    issuer = ALICE.id if is_issuer else PrincipalId(UUID(int=99))
    s.facts.revocation = replace(
        s.facts.revocation,
        actor=replace(
            ACTOR,
            grants=(
                OrganizationActionGrantDTO(action_id=ActionId("admit-users"), can_grant=can_grant),
            ),
        ),
        invitation=replace(ORIGINAL, issuer_principal_id=issuer),
    )
    if allowed:
        assert (
            await s.service.revoke(access=ACCESS, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
        ).access_revision == 8
    else:
        with pytest.raises(AccessDeniedError):
            await s.service.revoke(access=ACCESS, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
        assert "reserve" not in s.events and s.writer.revoked is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "actor",
    [
        replace(ACTOR, grants=()),
        replace(ACTOR, has_pending_recovery=True),
        replace(ACTOR, principal=replace(ALICE, status=PrincipalStatus.SUSPENDED)),
        replace(ACTOR, principal=replace(ALICE, kind=PrincipalKind.APPLICATION)),
    ],
)
async def test_current_revocation_denial_precedes_original_metadata(
    actor: OrganizationAccessFactsDTO,
) -> None:
    s = _revocation_scenario()
    assert s.facts.revocation is not None
    s.facts.revocation = replace(s.facts.revocation, actor=actor)
    s.idempotency.result = replace(REVOKE_COMPLETED, created=False)
    with pytest.raises(AccessDeniedError):
        await s.service.revoke(access=ACCESS, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
    assert "reserve" not in s.events and "revoke_original" not in s.events


@pytest.mark.asyncio
async def test_revocation_requires_current_oauth_evidence_before_original() -> None:
    s = _revocation_scenario()
    access = AccessContextDTO(
        actor_principal_id=ALICE.id,
        authentication_evidence=MockAuthenticationEvidence.human_oauth(IDENTITY),
    )
    assert s.facts.revocation is not None
    s.facts.revocation = replace(
        s.facts.revocation,
        actor=replace(
            ACTOR,
            oauth_credential_facts=HumanCredentialFactsDTO(
                binding_matches_actor=True, current_version=HumanCredentialVersion(2)
            ),
        ),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await s.service.revoke(access=access, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
    assert "reserve" not in s.events


@pytest.mark.asyncio
async def test_fresh_revocation_checks_reviewed_revision() -> None:
    s = _revocation_scenario()
    with pytest.raises(StaleRevisionError):
        await s.service.revoke(
            access=ACCESS,
            command=replace(REVOKE_COMMAND, expected_access_revision=6),
            context=REVOKE_CONTEXT,
        )
    assert "complete" not in s.events and s.writer.revoked is None


@pytest.mark.asyncio
async def test_already_revoked_request_preserves_revision_and_revocation_time() -> None:
    s = _revocation_scenario()
    assert s.facts.revocation is not None
    s.facts.revocation = replace(s.facts.revocation, invitation=replace(ORIGINAL, revoked_at=NOW))
    result = await s.service.revoke(access=ACCESS, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
    assert result.access_revision == 7 and s.writer.revoked is not None
    assert s.writer.revoked[-1] == NOW


@pytest.mark.asyncio
async def test_revocation_writer_failure_rolls_back_completed_reservation() -> None:
    s = _revocation_scenario()
    s.writer.error = ConflictError("Controlled revocation failure")
    with pytest.raises(ConflictError):
        await s.service.revoke(access=ACCESS, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
    assert s.events[-2:] == ["revoke_save", "rollback"]


@pytest.mark.asyncio
async def test_revocation_rejects_changed_native_route_before_reading_facts() -> None:
    s = _revocation_scenario()
    with pytest.raises(RuntimeError) as error:
        await s.service.revoke(
            access=ACCESS,
            command=REVOKE_COMMAND,
            context=replace(REVOKE_CONTEXT, requested_route="/v1/invitations/other/revoke"),
        )
    assert type(error.value) is RuntimeError and s.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [True, False])
async def test_revocation_original_must_match_the_recovered_binding(missing: bool) -> None:
    s = _revocation_scenario()
    s.idempotency.result = replace(REVOKE_COMPLETED, created=False)
    s.facts.revocation_original = (
        None
        if missing
        else InvitationRevocationResultDTO(
            invitation_id=InvitationId(UUID(int=999)),
            organization_id=ORG,
            access_revision=8,
            operation=s.idempotency.result,
        )
    )
    with pytest.raises((DependencyUnavailableError, RuntimeError)) as error:
        await s.service.revoke(access=ACCESS, command=REVOKE_COMMAND, context=REVOKE_CONTEXT)
    assert type(error.value) is (DependencyUnavailableError if missing else RuntimeError)
    assert s.writer.revoked is None


def test_revocation_fingerprint_binds_exact_invitation_and_review() -> None:
    s = _revocation_scenario()
    original = s.fingerprints.for_revoke(REVOKE_COMMAND)
    assert original != s.fingerprints.for_revoke(
        replace(REVOKE_COMMAND, invitation_id=InvitationId(UUID(int=999)))
    )
    assert original != s.fingerprints.for_revoke(
        replace(REVOKE_COMMAND, expected_access_revision=8)
    )
    assert original != s.fingerprints.for_issue(COMMAND)


@pytest.mark.parametrize("revision", [True, -1, 2**53])
def test_revocation_rejects_invalid_reviewed_revision(revision: int) -> None:
    with pytest.raises((TypeError, ValueError)):
        RevokeInvitationCommand(
            invitation_id=ORIGINAL.invitation_id, expected_access_revision=revision
        )


def test_revocation_accepts_zero_as_a_review_to_be_compared_with_current_state() -> None:
    assert (
        RevokeInvitationCommand(
            invitation_id=ORIGINAL.invitation_id, expected_access_revision=0
        ).expected_access_revision
        == 0
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
@pytest.mark.parametrize("operation", ["issue", "revoke", "project"])
async def test_browser_currentness_preserves_the_presented_credential_family(
    oauth: bool, operation: str
) -> None:
    """Reject stale evidence before disclosing data, recovering originals or changing authority."""
    evidence = (
        MockAuthenticationEvidence.human_oauth() if oauth else MockAuthenticationEvidence.browser()
    )
    stale = HumanCredentialFactsDTO(True, HumanCredentialVersion(2))
    expected = HumanOAuthCredentialRejectedError if oauth else AuthenticationRequiredError
    scenario = _Scenario()
    access = replace(ACCESS, authentication_evidence=evidence)
    command = COMMAND
    if operation == "revoke":
        assert scenario.facts.revocation is not None
        scenario.facts.revocation = replace(
            scenario.facts.revocation, actor=replace(ACTOR, oauth_credential_facts=stale)
        )
    elif operation == "project":
        command = _with_intent(
            scenario, InvitationProjectMembershipIntentDTO(project_id=PROJECT), project=True
        )
        assert scenario.facts.value is not None
        observed = scenario.facts.value.assignments[0]
        assert observed.project is not None
        observed = replace(
            observed,
            project=replace(
                observed.project,
                action=replace(observed.project.action, oauth_credential_facts=stale),
            ),
        )
        scenario.facts.value = replace(scenario.facts.value, assignments=(observed,))
    else:
        scenario.facts.value = replace(FACTS, actor=replace(ACTOR, oauth_credential_facts=stale))
    with pytest.raises(AuthenticationRequiredError) as caught:
        if operation == "revoke":
            await scenario.service.revoke(
                access=access, command=REVOKE_COMMAND, context=REVOKE_CONTEXT
            )
        else:
            await scenario.service.issue(access=access, command=command, context=CONTEXT)
    assert type(caught.value) is expected
    assert (
        "reserve" not in scenario.events
        and "original" not in scenario.events
        and "revoke_original" not in scenario.events
    )
    assert scenario.writer.saved is None
