"""Preview valid intent without product admission, password I/O or operation reservation."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import MockTransactions

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
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
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_browser_proof_dto import (
    InvitationBrowserProofDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_pipeline_target_dto import (
    InvitationPipelineTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_preview_facts_dto import (
    InvitationPreviewFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_preview_result_dto import (
    InvitationPreviewResultDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_scope_dto import InvitationScopeDTO
from inframeld_backend.access.application.dtos.invitation_target_dto import InvitationTargetDTO
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.invitation_preview_facts_reader import (
    InvitationPreviewFactsReader,
)
from inframeld_backend.access.application.queries.preview_invitation_query import (
    PreviewInvitationQuery,
)
from inframeld_backend.access.application.services.invitation_preview_service import (
    InvitationPreviewService,
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
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ORG = OrganizationId(UUID(int=1))
IDENTITY = VerifiedHumanIdentityDTO(
    authority=IdentityAuthority("kratos:test"), subject=IdentitySubject(str(UUID(int=2)))
)
BOB = Principal(
    id=PrincipalId(UUID(int=3)),
    organization_id=ORG,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
TOKEN = InvitationToken("A" * 43)
QUERY = PreviewInvitationQuery(token=TOKEN)
PROOF = InvitationBrowserProofDTO(identity=IDENTITY, password_completed=None)
NOW = datetime.now(UTC)
RECORD = InvitationRecordDTO(
    invitation_id=InvitationId(UUID(int=4)),
    organization_id=ORG,
    issuer_principal_id=PrincipalId(UUID(int=5)),
    digest=TOKEN.digest(),
    assignments=(InvitationAdmissionOnlyIntentDTO(),),
    issued_operation_id=OperationId("issued-original"),
    issued_access_revision=7,
    issued_at=NOW - timedelta(hours=1),
    expires_at=NOW + timedelta(days=7),
)
STATE = HumanCredentialStateDTO(
    installation_id=InstallationId(UUID(int=6)),
    identity=IDENTITY,
    version=None,
    has_pending_recovery=False,
)
BASELINE = InvitationScopeDTO(
    target=OrganizationGrantTargetDTO(organization_id=ORG), display_name="Example Organization"
)
FACTS = InvitationPreviewFactsDTO(
    invitation=RECORD,
    principal=None,
    credential_state=STATE,
    has_credential_history=False,
    scopes=(BASELINE,),
)


class _Reader(InvitationPreviewFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: InvitationPreviewFactsDTO | None = FACTS
        self.error: Exception | None = None

    @override
    async def read_preview(
        self, *, identity: VerifiedHumanIdentityDTO, digest: InvitationTokenDigest
    ) -> InvitationPreviewFactsDTO | None:
        self.events.append("read")
        assert identity == IDENTITY and digest.matches(TOKEN.digest())
        if self.error is not None:
            raise self.error
        return self.result


def _scenario() -> tuple[InvitationPreviewService, _Reader, list[str]]:
    events: list[str] = []
    reader = _Reader(events)
    service = InvitationPreviewService(
        transaction_manager=MockTransactions(events), invitation_preview_facts_reader=reader
    )
    return service, reader, events


@pytest.mark.asyncio
@pytest.mark.parametrize("password", [None, False, True])
async def test_unadmitted_preview_requires_no_password_observation_or_reservation(
    password: bool | None,
) -> None:
    service, _, events = _scenario()
    result = await service.preview(proof=replace(PROOF, password_completed=password), query=QUERY)
    assert result == InvitationPreviewResultDTO(
        invitation_id=RECORD.invitation_id,
        organization_id=ORG,
        assignments=RECORD.assignments,
        expires_at=RECORD.expires_at,
        scopes=(BASELINE,),
    )
    assert events == ["begin", "read", "commit"]


@pytest.mark.asyncio
async def test_current_eligible_admitted_human_can_preview_without_reinitializing_version() -> None:
    service, reader, events = _scenario()
    reader.result = replace(
        FACTS,
        principal=BOB,
        credential_state=replace(STATE, version=HumanCredentialVersion(8)),
        has_credential_history=True,
    )
    assert (await service.preview(proof=PROOF, query=QUERY)).invitation_id == RECORD.invitation_id
    assert events == ["begin", "read", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record",
    [
        replace(RECORD, issued_at=NOW - timedelta(days=8), expires_at=NOW - timedelta(days=1)),
        replace(RECORD, revoked_at=NOW),
        replace(RECORD, consumed_at=NOW, consumed_by_principal_id=BOB.id),
    ],
)
async def test_invalid_fresh_token_state_is_hidden_before_recipient_conflict(
    record: InvitationRecordDTO,
) -> None:
    service, reader, _ = _scenario()
    reader.result = replace(
        FACTS, invitation=record, credential_state=replace(STATE, has_pending_recovery=True)
    )
    with pytest.raises(ResourceNotFoundError):
        await service.preview(proof=PROOF, query=QUERY)


@pytest.mark.asyncio
async def test_unknown_digest_is_uniformly_hidden() -> None:
    service, reader, _ = _scenario()
    reader.result = None
    with pytest.raises(ResourceNotFoundError):
        await service.preview(proof=PROOF, query=QUERY)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "principal",
    [
        replace(BOB, status=PrincipalStatus.SUSPENDED),
        replace(BOB, organization_id=OrganizationId(UUID(int=99))),
        replace(BOB, kind=PrincipalKind.APPLICATION),
    ],
)
async def test_current_linked_recipient_restrictions_are_not_bypassed(principal: Principal) -> None:
    service, reader, _ = _scenario()
    reader.result = replace(FACTS, principal=principal)
    with pytest.raises(ConflictError):
        await service.preview(proof=PROOF, query=QUERY)


@pytest.mark.asyncio
async def test_recovery_block_applies_before_any_local_link_exists() -> None:
    service, reader, _ = _scenario()
    reader.result = replace(FACTS, credential_state=replace(STATE, has_pending_recovery=True))
    with pytest.raises(ConflictError):
        await service.preview(proof=PROOF, query=QUERY)


@pytest.mark.asyncio
async def test_retained_history_without_current_version_is_unavailable() -> None:
    service, reader, _ = _scenario()
    reader.result = replace(FACTS, has_credential_history=True)
    with pytest.raises(DependencyUnavailableError):
        await service.preview(proof=PROOF, query=QUERY)


@pytest.mark.asyncio
async def test_stale_targets_are_conflicts_without_partial_scope() -> None:
    service, reader, _ = _scenario()
    reader.result = replace(FACTS, scopes=None)
    with pytest.raises(ConflictError):
        await service.preview(proof=PROOF, query=QUERY)


@pytest.mark.asyncio
async def test_preview_cannot_return_inventory_beyond_intended_targets() -> None:
    service, reader, _ = _scenario()
    reader.result = replace(
        FACTS,
        scopes=(
            BASELINE,
            InvitationScopeDTO(
                target=ProjectGrantTargetDTO(project_id=ProjectId(UUID(int=99))),
                display_name="Private other Project",
            ),
        ),
    )
    with pytest.raises(RuntimeError) as error:
        await service.preview(proof=PROOF, query=QUERY)
    assert type(error.value) is RuntimeError


@pytest.mark.asyncio
@pytest.mark.parametrize("binding", ["identity", "digest"])
async def test_preview_requires_exact_verified_identity_and_digest(binding: str) -> None:
    service, reader, _ = _scenario()
    if binding == "identity":
        reader.result = replace(
            FACTS,
            credential_state=replace(
                STATE, identity=replace(IDENTITY, subject=IdentitySubject("other"))
            ),
        )
    else:
        reader.result = replace(
            FACTS, invitation=replace(RECORD, digest=InvitationToken("B" + "A" * 42).digest())
        )
    with pytest.raises(RuntimeError) as error:
        await service.preview(proof=PROOF, query=QUERY)
    assert type(error.value) is RuntimeError


@pytest.mark.asyncio
async def test_multiple_effects_share_one_authoritative_project_scope() -> None:
    service, reader, _ = _scenario()
    project = ProjectId(UUID(int=20))
    group = AccessGroupId(UUID(int=21))
    assignments = (
        InvitationProjectMembershipIntentDTO(project_id=project),
        InvitationGroupMembershipIntentDTO(project_id=project, access_group_id=group),
    )
    scopes = (
        BASELINE,
        InvitationScopeDTO(
            target=ProjectGrantTargetDTO(project_id=project), display_name="Support"
        ),
        InvitationScopeDTO(
            target=AccessGroupGrantTargetDTO(project_id=project, access_group_id=group),
            display_name="SupportKnowledge",
        ),
    )
    reader.result = replace(
        FACTS, invitation=replace(RECORD, assignments=assignments), scopes=scopes
    )
    result = await service.preview(proof=PROOF, query=QUERY)
    assert result.scopes == scopes and result.assignments == assignments


@pytest.mark.asyncio
async def test_hundred_distinct_group_effects_fit_201_safe_scopes_without_membership() -> None:
    service, reader, _ = _scenario()
    assignments = tuple(
        InvitationGroupMembershipIntentDTO(
            project_id=ProjectId(UUID(int=100 + i)),
            access_group_id=AccessGroupId(UUID(int=1000 + i)),
        )
        for i in range(100)
    )
    scopes = (BASELINE,) + tuple(
        scope
        for i, intent in enumerate(assignments)
        for scope in (
            InvitationScopeDTO(
                target=ProjectGrantTargetDTO(project_id=intent.project_id),
                display_name=f"Project{i}",
            ),
            InvitationScopeDTO(
                target=AccessGroupGrantTargetDTO(
                    project_id=intent.project_id, access_group_id=intent.access_group_id
                ),
                display_name=f"Group{i}",
            ),
        )
    )
    reader.result = replace(
        FACTS, invitation=replace(RECORD, assignments=assignments), scopes=scopes
    )
    result = await service.preview(proof=PROOF, query=QUERY)
    assert len(result.scopes) == 201 and result.assignments == assignments


@pytest.mark.asyncio
async def test_future_target_does_not_create_an_imaginary_resource_producer() -> None:
    service, reader, _ = _scenario()
    target = InvitationPipelineTargetDTO(pipeline_id=UUID(int=90))
    assignment = InvitationActionGrantIntentDTO(
        target=target, action_id=ActionId("edit-pipeline"), can_grant=False
    )
    reader.result = replace(
        FACTS,
        invitation=replace(RECORD, assignments=(assignment,)),
        scopes=(BASELINE, InvitationScopeDTO(target=target, display_name="Unimplemented pipeline")),
    )
    with pytest.raises(ConflictError):
        await service.preview(proof=PROOF, query=QUERY)


@pytest.mark.asyncio
async def test_wrong_action_catalogue_cannot_be_previewed_as_supported_intent() -> None:
    service, reader, _ = _scenario()
    target = ProjectGrantTargetDTO(project_id=ProjectId(UUID(int=20)))
    assignment = InvitationActionGrantIntentDTO(
        target=target, action_id=ActionId("add-documents"), can_grant=False
    )
    reader.result = replace(
        FACTS,
        invitation=replace(RECORD, assignments=(assignment,)),
        scopes=(BASELINE, InvitationScopeDTO(target=target, display_name="Support")),
    )
    with pytest.raises(ConflictError):
        await service.preview(proof=PROOF, query=QUERY)


@pytest.mark.asyncio
async def test_reader_failure_rolls_back_and_propagates_without_private_scope() -> None:
    service, reader, events = _scenario()
    reader.error = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await service.preview(proof=PROOF, query=QUERY)
    assert events == ["begin", "read", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "target,action",
    [
        (OrganizationGrantTargetDTO(organization_id=ORG), "create-projects"),
        (ProjectGrantTargetDTO(project_id=ProjectId(UUID(int=20))), "create-access-groups"),
        (
            AccessGroupGrantTargetDTO(
                project_id=ProjectId(UUID(int=20)), access_group_id=AccessGroupId(UUID(int=21))
            ),
            "add-documents",
        ),
        (
            ApplicationAccountGrantTargetDTO(
                project_id=ProjectId(UUID(int=20)),
                application_principal_id=PrincipalId(UUID(int=22)),
            ),
            "issue-application-keys",
        ),
    ],
)
@pytest.mark.parametrize("can_grant", [False, True])
async def test_supported_human_grants_show_exact_current_target_scopes(
    target: InvitationTargetDTO, action: str, can_grant: bool
) -> None:
    service, reader, _ = _scenario()
    assignment = InvitationActionGrantIntentDTO(
        target=target, action_id=ActionId(action), can_grant=can_grant
    )
    scopes = [BASELINE]
    if isinstance(
        target, (ProjectGrantTargetDTO, AccessGroupGrantTargetDTO, ApplicationAccountGrantTargetDTO)
    ):
        scopes.append(
            InvitationScopeDTO(
                target=ProjectGrantTargetDTO(project_id=target.project_id), display_name="Support"
            )
        )
    if isinstance(target, (AccessGroupGrantTargetDTO, ApplicationAccountGrantTargetDTO)):
        scopes.append(InvitationScopeDTO(target=target, display_name="Intended target"))
    reader.result = replace(
        FACTS, invitation=replace(RECORD, assignments=(assignment,)), scopes=tuple(scopes)
    )
    result = await service.preview(proof=PROOF, query=QUERY)
    assert result.assignments == (assignment,) and result.scopes == tuple(scopes)
