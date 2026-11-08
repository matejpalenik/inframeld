"""Recover a current recipient's original before fresh activation prerequisites."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import MockTransactions

from inframeld_backend.access.application.commands.activate_invitation_command import (
    ActivateInvitationCommand,
)
from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_facts_dto import (
    InvitationActivationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_result_dto import (
    InvitationActivationResultDTO,
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
from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
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
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.invitation_activation_operation_store import (
    InvitationActivationOperationStore,
)
from inframeld_backend.access.application.protocols.invitation_admission_writer import (
    InvitationAdmissionWriter,
)
from inframeld_backend.access.application.protocols.invitation_assignment_facts_reader import (
    InvitationAssignmentFactsReader,
)
from inframeld_backend.access.application.services.invitation_activation_service import (
    InvitationActivationService,
)
from inframeld_backend.access.application.services.invitation_assignment_service import (
    InvitationAssignmentService,
)
from inframeld_backend.access.application.services.invitation_fingerprint_service import (
    InvitationFingerprintService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
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
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

NOW = datetime.now(UTC)
ORG = OrganizationId(UUID(int=1))
PROJECT = ProjectId(UUID(int=2))
IDENTITY = VerifiedHumanIdentityDTO(
    authority=IdentityAuthority("kratos:test"), subject=IdentitySubject(str(UUID(int=3)))
)
BOB = Principal(
    id=PrincipalId(UUID(int=4)),
    organization_id=ORG,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
TOKEN = InvitationToken("A" * 43)
RECORD = InvitationRecordDTO(
    invitation_id=InvitationId(UUID(int=5)),
    organization_id=ORG,
    issuer_principal_id=PrincipalId(UUID(int=6)),
    digest=TOKEN.digest(),
    assignments=(
        InvitationGroupMembershipIntentDTO(
            project_id=PROJECT, access_group_id=AccessGroupId(UUID(int=7))
        ),
    ),
    issued_operation_id=OperationId("issued"),
    issued_access_revision=1,
    issued_at=NOW - timedelta(days=8),
    expires_at=NOW - timedelta(days=1),
    consumed_at=NOW - timedelta(days=2),
    consumed_by_principal_id=BOB.id,
)
FACTS = InvitationActivationFactsDTO(
    invitation=RECORD,
    principal=BOB,
    credential_state=HumanCredentialStateDTO(
        installation_id=InstallationId(UUID(int=8)),
        identity=IDENTITY,
        version=HumanCredentialVersion(2),
        has_pending_recovery=False,
    ),
    has_credential_history=True,
    current_time=NOW,
    organization_access_revision=7,
)
ORIGINAL = InvitationActivationResultDTO(
    invitation_id=RECORD.invitation_id,
    organization_id=ORG,
    principal_id=BOB.id,
    organization_access_revision=8,
    project_access_revisions=(
        InvitationProjectAccessRevisionDTO(project_id=PROJECT, access_revision=9),
    ),
    operation=CompletedSynchronousOperationDTO(
        operation_id=OperationId("activation-original"),
        created=False,
        replay_kind=OperationReplayKind.SAFE_RESULT,
        expires_at=NOW + timedelta(hours=1),
    ),
)
CONTEXT = IdempotencyContextDTO(
    method=HttpMethod.POST,
    requested_route="/v1/invitations/activate",
    key=IdempotencyKey("lost-activation"),
)


class _Facts(InvitationAssignmentFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.value: InvitationActivationFactsDTO | None = FACTS
        self.error: Exception | None = None
        self.issuer: InvitationIssuerFactsDTO | None = None

    @override
    async def lock_for_activation(
        self, *, identity: VerifiedHumanIdentityDTO, digest: InvitationTokenDigest
    ) -> InvitationActivationFactsDTO | None:
        assert identity == IDENTITY and digest.matches(TOKEN.digest())
        self.events.append("facts")
        if self.error is not None:
            raise self.error
        return self.value

    @override
    async def read_current_issuer(
        self, *, invitation: InvitationRecordDTO
    ) -> InvitationIssuerFactsDTO | None:
        self.events.append("issuer")
        assert self.value is not None and invitation == self.value.invitation
        return self.issuer

    @override
    async def read_assignment_states(
        self, *, invitation: InvitationRecordDTO, recipient: Principal | None
    ) -> tuple[InvitationAssignmentStateDTO, ...] | None:
        raise AssertionError("Admission-only replay must not read assignment state.")

    @override
    async def read_assignment_state(
        self, *, invitation_id: InvitationId, recipient: Principal, intent: InvitationAssignmentDTO
    ) -> InvitationAssignmentStateDTO | None:
        raise AssertionError("Admission-only replay must not refresh assignment state.")


class _Store(InvitationActivationOperationStore):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.value: InvitationActivationResultDTO | None = ORIGINAL
        self.error: Exception | None = None
        self.principal: Principal | None = None
        self.bound_principal: PrincipalId | None = None

    @override
    async def read_activation_original(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        organization_id: OrganizationId,
        invitation_id: InvitationId,
        principal_id: PrincipalId | None,
        context: IdempotencyContextDTO,
        fingerprint: RequestFingerprint,
    ) -> InvitationActivationResultDTO | None:
        assert (
            identity == IDENTITY
            and organization_id == ORG
            and invitation_id == RECORD.invitation_id
        )
        assert installation_id == FACTS.credential_state.installation_id
        assert context == CONTEXT
        self.events.append("original")
        if self.error is not None:
            raise self.error
        return self.value

    @override
    async def reserve_activation(
        self,
        *,
        installation_id: InstallationId,
        identity: VerifiedHumanIdentityDTO,
        invitation: InvitationRecordDTO,
        principal_id: PrincipalId | None,
        context: IdempotencyContextDTO,
        fingerprint: RequestFingerprint,
    ) -> InvitationActivationBindingDTO:
        self.events.append("reserve")
        assert identity == IDENTITY and invitation.digest.matches(TOKEN.digest())
        assert context == CONTEXT and installation_id == FACTS.credential_state.installation_id
        return InvitationActivationBindingDTO(
            operation_id=OperationId("activation-fresh"),
            installation_id=installation_id,
            identity=identity,
            organization_id=invitation.organization_id,
            invitation_id=invitation.invitation_id,
            issuer_principal_id=invitation.issuer_principal_id,
            principal_id=principal_id,
            context=context,
            fingerprint=fingerprint,
        )

    @override
    async def bind_activation_principal(
        self, *, binding: InvitationActivationBindingDTO, principal: Principal
    ) -> InvitationActivationBindingDTO:
        self.events.append("bind")
        self.principal = principal
        self.bound_principal = principal.id
        return replace(binding, principal_id=principal.id)

    @override
    async def complete_activation(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        digest: InvitationTokenDigest,
        organization_access_revision: int,
        project_access_revisions: tuple[InvitationProjectAccessRevisionDTO, ...],
    ) -> InvitationActivationResultDTO:
        self.events.append("complete")
        assert binding.principal_id is not None and digest.matches(TOKEN.digest())
        return InvitationActivationResultDTO(
            invitation_id=binding.invitation_id,
            organization_id=binding.organization_id,
            principal_id=binding.principal_id,
            organization_access_revision=organization_access_revision,
            project_access_revisions=project_access_revisions,
            operation=replace(ORIGINAL.operation, operation_id=binding.operation_id, created=True),
        )


class _Admission(InvitationAdmissionWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.calls: list[tuple[InvitationActivationBindingDTO, Principal]] = []
        self.error: Exception | None = None

    @override
    async def apply_invitation_admission(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: InvitationActivationFactsDTO,
        issuer: InvitationIssuerFactsDTO,
        principal: Principal,
    ) -> int:
        self.events.append("admit")
        assert binding.issuer_principal_id == issuer.organization_access.principal.id
        assert binding.identity == facts.credential_state.identity
        self.calls.append((binding, principal))
        if self.error is not None:
            raise self.error
        return facts.organization_access_revision + (facts.principal is None)


class _Assignments(InvitationAssignmentService):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    @override
    async def prepare(
        self, *, facts: InvitationActivationFactsDTO, issuer: InvitationIssuerFactsDTO
    ) -> tuple[InvitationAssignmentStateDTO, ...]:
        assert len(facts.invitation.assignments) == 1 and isinstance(
            facts.invitation.assignments[0], InvitationAdmissionOnlyIntentDTO
        )
        self.events.append("prepare")
        return ()

    @override
    async def apply(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        principal: Principal,
        states: tuple[InvitationAssignmentStateDTO, ...],
        organization_access_revision: int,
    ) -> tuple[int, tuple[InvitationProjectAccessRevisionDTO, ...]]:
        assert states == () and binding.principal_id == principal.id
        self.events.append("assignments")
        return organization_access_revision, ()


@pytest.mark.asyncio
async def test_current_recipient_recovers_original_after_expiry_without_password_or_membership() -> (
    None
):
    events: list[str] = []
    service = InvitationActivationService(
        transaction_manager=MockTransactions(events),
        invitation_assignment_facts_reader=_Facts(events),
        invitation_activation_operation_store=_Store(events),
        invitation_admission_writer=_Admission(events),
        invitation_assignment_service=_Assignments(events),
        invitation_fingerprint_service=InvitationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
        ),
    )
    result = await service.activate(
        proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None),
        command=ActivateInvitationCommand(token=TOKEN),
        context=CONTEXT,
    )
    assert result == ORIGINAL
    assert events == ["begin", "facts", "original", "commit"]


def _scenario() -> tuple[InvitationActivationService, _Facts, _Store, list[str]]:
    events: list[str] = []
    facts, store = _Facts(events), _Store(events)
    service = InvitationActivationService(
        transaction_manager=MockTransactions(events),
        invitation_assignment_facts_reader=facts,
        invitation_activation_operation_store=store,
        invitation_admission_writer=_Admission(events),
        invitation_assignment_service=_Assignments(events),
        invitation_fingerprint_service=InvitationFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
        ),
    )
    return service, facts, store, events


@pytest.mark.asyncio
@pytest.mark.parametrize("password", [False, True])
async def test_completed_replay_does_not_reapply_password_observation(password: bool) -> None:
    service, _, _, events = _scenario()
    assert (
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=password),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
        == ORIGINAL
    )
    assert events == ["begin", "facts", "original", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "principal",
    [
        replace(BOB, status=PrincipalStatus.SUSPENDED),
        replace(BOB, organization_id=OrganizationId(UUID(int=99))),
        replace(BOB, kind=PrincipalKind.APPLICATION),
    ],
)
async def test_current_recipient_restrictions_precede_completed_original(
    principal: Principal,
) -> None:
    service, facts, _, events = _scenario()
    facts.value = replace(FACTS, principal=principal)
    with pytest.raises(ConflictError):
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_recovery_block_cannot_read_completed_outcome() -> None:
    service, facts, _, events = _scenario()
    facts.value = replace(
        FACTS, credential_state=replace(FACTS.credential_state, has_pending_recovery=True)
    )
    with pytest.raises(ConflictError):
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert "original" not in events


@pytest.mark.asyncio
async def test_missing_current_version_with_history_is_not_reinitialized_on_replay() -> None:
    service, facts, _, events = _scenario()
    facts.value = replace(FACTS, credential_state=replace(FACTS.credential_state, version=None))
    with pytest.raises(DependencyUnavailableError):
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert "original" not in events


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["identity", "digest"])
async def test_activation_facts_keep_exact_current_identity_and_token(mismatch: str) -> None:
    service, facts, _, events = _scenario()
    facts.value = (
        replace(
            FACTS,
            credential_state=replace(
                FACTS.credential_state, identity=replace(IDENTITY, subject=IdentitySubject("other"))
            ),
        )
        if mismatch == "identity"
        else replace(
            FACTS, invitation=replace(RECORD, digest=InvitationToken("B" + "A" * 42).digest())
        )
    )
    with pytest.raises(RuntimeError) as error:
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert type(error.value) is RuntimeError and "original" not in events


@pytest.mark.asyncio
async def test_unknown_activation_token_has_no_original_or_fresh_effects() -> None:
    service, facts, _, events = _scenario()
    facts.value = None
    with pytest.raises(ResourceNotFoundError):
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert "original" not in events


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", ["principal", "invitation", "organization", "kind"])
async def test_completed_activation_must_match_current_recipient_and_original_binding(
    mismatch: str,
) -> None:
    service, _, store, _ = _scenario()
    store.value = (
        replace(ORIGINAL, principal_id=PrincipalId(UUID(int=99)))
        if mismatch == "principal"
        else replace(ORIGINAL, invitation_id=InvitationId(UUID(int=99)))
        if mismatch == "invitation"
        else replace(ORIGINAL, organization_id=OrganizationId(UUID(int=99)))
        if mismatch == "organization"
        else replace(
            ORIGINAL,
            operation=replace(ORIGINAL.operation, replay_kind=OperationReplayKind.ISSUED_SECRET),
        )
    )
    with pytest.raises((RuntimeError, ConflictError)) as error:
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert type(error.value) in (RuntimeError, ConflictError)


@pytest.mark.asyncio
async def test_activation_rejects_nonliteral_native_route_before_current_facts() -> None:
    service, _, _, events = _scenario()
    with pytest.raises(RuntimeError) as error:
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None),
            command=ActivateInvitationCommand(token=TOKEN),
            context=replace(CONTEXT, requested_route="/v1/invitations/activate?other=true"),
        )
    assert type(error.value) is RuntimeError and events == []


def test_activation_fingerprint_binds_invitation_and_token_without_a_new_key_namespace() -> None:
    fingerprints = InvitationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32))
    )
    command = ActivateInvitationCommand(token=TOKEN)
    original = fingerprints.for_activation(command, invitation_id=RECORD.invitation_id)
    assert original == fingerprints.for_activation(command, invitation_id=RECORD.invitation_id)
    assert original != fingerprints.for_activation(
        command, invitation_id=InvitationId(UUID(int=99))
    )
    assert original != fingerprints.for_activation(
        ActivateInvitationCommand(token=InvitationToken("B" + "A" * 42)),
        invitation_id=RECORD.invitation_id,
    )


def _fresh() -> tuple[InvitationActivationService, _Facts, _Store, list[str]]:
    service, facts, store, events = _scenario()
    intent = InvitationAdmissionOnlyIntentDTO()
    record = replace(
        RECORD,
        assignments=(intent,),
        expires_at=NOW + timedelta(days=1),
        consumed_at=None,
        consumed_by_principal_id=None,
    )
    facts.value = replace(FACTS, invitation=record)
    facts.issuer = InvitationIssuerFactsDTO(
        organization_access=OrganizationAccessFactsDTO(
            principal=replace(BOB, id=record.issuer_principal_id),
            access_revision=7,
            grants=(
                OrganizationActionGrantDTO(action_id=ActionId("admit-users"), can_grant=False),
            ),
            has_pending_recovery=False,
            oauth_credential_facts=None,
        ),
        has_coherent_identity=True,
        assignments=(
            InvitationAssignmentFactsDTO(
                intent=intent,
                project=None,
                target_exists=True,
                actor_can_grant=False,
                actor_is_group_member=False,
                actor_is_group_manager=False,
            ),
        ),
    )
    store.value = None
    return service, facts, store, events


@pytest.mark.asyncio
async def test_fresh_admission_keeps_existing_principal_and_issuer_attribution() -> None:
    service, _, store, events = _fresh()
    result = await service.activate(
        proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=True),
        command=ActivateInvitationCommand(token=TOKEN),
        context=CONTEXT,
    )
    assert result.principal_id == BOB.id and result.organization_access_revision == 7
    assert result.project_access_revisions == ()
    assert result.operation.created is True
    assert result.operation.operation_id == OperationId("activation-fresh")
    assert store.bound_principal == BOB.id
    assert events == [
        "begin",
        "facts",
        "original",
        "issuer",
        "prepare",
        "reserve",
        "admit",
        "bind",
        "assignments",
        "complete",
        "commit",
    ]


@pytest.mark.asyncio
async def test_fresh_admission_creates_one_human_after_current_issuer_checks() -> None:
    service, facts, store, events = _fresh()
    assert facts.value is not None
    facts.value = replace(
        facts.value,
        principal=None,
        has_credential_history=False,
        credential_state=replace(facts.value.credential_state, version=None),
    )
    result = await service.activate(
        proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=True),
        command=ActivateInvitationCommand(token=TOKEN),
        context=CONTEXT,
    )
    assert store.principal is not None
    assert result.principal_id == store.principal.id and result.organization_access_revision == 8
    assert store.principal.organization_id == ORG
    assert (
        store.principal.kind is PrincipalKind.HUMAN
        and store.principal.status is PrincipalStatus.ACTIVE
    )
    assert events.index("issuer") < events.index("reserve") < events.index("admit")


@pytest.mark.asyncio
@pytest.mark.parametrize("password", [False, None])
async def test_fresh_activation_requires_observed_password_completion(
    password: bool | None,
) -> None:
    service, _, _, events = _fresh()
    error = ConflictError if password is False else DependencyUnavailableError
    with pytest.raises(error):
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=password),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert events == ["begin", "facts", "original", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["expired", "equality", "revoked", "consumed"])
async def test_fresh_activation_denies_invalid_token_before_issuer_or_writes(invalid: str) -> None:
    service, facts, _, events = _fresh()
    assert facts.value is not None
    record = facts.value.invitation
    record = (
        replace(record, expires_at=NOW - timedelta(seconds=1))
        if invalid == "expired"
        else (
            replace(record, expires_at=NOW)
            if invalid == "equality"
            else (
                replace(record, revoked_at=NOW)
                if invalid == "revoked"
                else replace(record, consumed_at=NOW, consumed_by_principal_id=BOB.id)
            )
        )
    )
    facts.value = replace(facts.value, invitation=record)
    with pytest.raises(ResourceNotFoundError):
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=True),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert events == ["begin", "facts", "original", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["absent", "suspended", "recovery", "incoherent", "authority"])
async def test_fresh_activation_rechecks_retained_issuer_current_account_and_admission_authority(
    invalid: str,
) -> None:
    service, facts, _, events = _fresh()
    issuer = facts.issuer
    assert issuer is not None
    actor = issuer.organization_access
    if invalid == "absent":
        facts.issuer = None
    elif invalid == "incoherent":
        facts.issuer = replace(issuer, has_coherent_identity=False)
    else:
        actor = (
            replace(actor, principal=replace(actor.principal, status=PrincipalStatus.SUSPENDED))
            if invalid == "suspended"
            else (
                replace(actor, has_pending_recovery=True)
                if invalid == "recovery"
                else replace(actor, grants=())
            )
        )
        facts.issuer = replace(issuer, organization_access=actor)
    with pytest.raises(ConflictError):
        await service.activate(
            proof=InvitationBrowserProofDTO(identity=IDENTITY, password_completed=True),
            command=ActivateInvitationCommand(token=TOKEN),
            context=CONTEXT,
        )
    assert events == ["begin", "facts", "original", "issuer", "rollback"]
