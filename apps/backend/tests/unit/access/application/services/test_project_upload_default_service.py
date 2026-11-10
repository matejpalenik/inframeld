from dataclasses import replace
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    SAVED_RESULT,
    MockOperationIdempotency,
)
from tests.support.mock_project_upload_defaults import (
    COMMAND,
    FACTS,
    NEW,
    OLD,
    ORIGINAL,
    A,
    B,
    C,
    MockUploadDefaultFactsReader,
    MockUploadDefaultRepository,
    MockUploadDefaultTransactions,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_upload_audience_dto import (
    ProjectUploadAudienceDTO,
)
from inframeld_backend.access.application.dtos.upload_default_group_facts_dto import (
    UploadDefaultGroupFactsDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.queries.get_project_upload_default_query import (
    GetProjectUploadDefaultQuery,
)
from inframeld_backend.access.application.services.project_upload_default_fingerprint_service import (
    ProjectUploadDefaultFingerprintService,
)
from inframeld_backend.access.application.services.project_upload_default_service import (
    ProjectUploadDefaultService,
)
from inframeld_backend.access.domain.entities.project_upload_default import ProjectUploadDefault
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId

CONTEXT = IdempotencyContextDTO(
    HttpMethod.PUT,
    f"/v1/projects/{PROJECT_ID.value}/upload-defaults",
    IdempotencyKey("default-original"),
)


@pytest.fixture
def setup() -> tuple[
    ProjectUploadDefaultService,
    MockUploadDefaultFactsReader,
    MockUploadDefaultRepository,
    MockOperationIdempotency,
    MockUploadDefaultTransactions,
    list[str],
]:
    from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
        RequestFingerprintKey,
    )

    events: list[str] = []
    facts = MockUploadDefaultFactsReader(events)
    repo = MockUploadDefaultRepository(events)
    idem = MockOperationIdempotency(events)
    idem.result = NEW_RESERVATION
    tx = MockUploadDefaultTransactions(events)
    service = ProjectUploadDefaultService(
        transaction_manager=tx,
        default_facts_reader=facts,
        default_repository=repo,
        operation_idempotency=idem,
        default_fingerprint_service=ProjectUploadDefaultFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"f" * 32))
        ),
    )
    return service, facts, repo, idem, tx, events


type Setup = tuple[
    ProjectUploadDefaultService,
    MockUploadDefaultFactsReader,
    MockUploadDefaultRepository,
    MockOperationIdempotency,
    MockUploadDefaultTransactions,
    list[str],
]


@pytest.mark.asyncio
async def test_fresh_change_saves_exact_transition_before_completion_and_commit(
    setup: Setup,
) -> None:
    service, _, repo, idem, _, events = setup
    result = await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.default.audience == NEW
    assert result.default.access_revision == 8
    assert repo.saved == [ORIGINAL]
    assert idem.lookup_authority is None
    assert events == [
        "begin",
        "lock-current",
        "reserve",
        "load",
        "save",
        "complete",
        "commit-attempt",
        "commit-confirmed",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("unset", [False, True])
async def test_get_reads_authoritative_saved_or_unconfigured_default(
    setup: Setup, unset: bool
) -> None:
    service, facts, _, idem, _, events = setup
    facts.facts = (
        replace(FACTS, audience=None, groups=())
        if unset
        else replace(FACTS, groups=FACTS.groups[:1])
    )
    result = await service.get(access=ACCESS, query=GetProjectUploadDefaultQuery(PROJECT_ID))
    assert result.audience == (None if unset else OLD)
    assert result.access_revision == 7
    assert idem.calls == 0
    assert events == ["begin", "read-current", "commit-attempt", "commit-confirmed"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "change",
    [
        "missing-project",
        "departed",
        "suspended",
        "recovering",
        "inactive-project",
        "missing-action",
    ],
)
async def test_current_eligibility_precedes_any_original(setup: Setup, change: str) -> None:
    service, facts, repo, idem, _, _ = setup
    idem.result = SAVED_RESULT
    action = FACTS.action
    expected: type[Exception] = AccessDeniedError
    match change:
        case "missing-project":
            facts.facts = None
            expected = ResourceNotFoundError
        case "departed":
            facts.facts = replace(FACTS, action=replace(action, is_project_member=False))
            expected = ResourceNotFoundError
        case "suspended":
            facts.facts = replace(
                FACTS,
                action=replace(
                    action, principal=replace(action.principal, status=PrincipalStatus.SUSPENDED)
                ),
            )
            expected = ResourceNotFoundError
        case "recovering":
            facts.facts = replace(FACTS, action=replace(action, has_pending_recovery=True))
        case "inactive-project":
            facts.facts = replace(
                FACTS, action=replace(action, project_status=ProjectStatus.DELETING)
            )
            expected = ResourceNotFoundError
        case _:
            facts.facts = replace(FACTS, action=replace(action, has_exact_action_grant=False))
    with pytest.raises(expected):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert idem.calls == 0
    assert not repo.saved


@pytest.mark.asyncio
@pytest.mark.parametrize("group_index", [0, 1])
@pytest.mark.parametrize("relationship", ["member", "manager"])
async def test_every_old_new_and_retained_group_requires_management(
    setup: Setup, group_index: int, relationship: str
) -> None:
    service, facts, _, idem, _, _ = setup
    groups = list(FACTS.groups)
    groups[group_index] = replace(
        groups[group_index],
        has_group_action=group_index == 1 and relationship == "member",
        **(
            {"is_member": False, "is_manager": False}
            if relationship == "member"
            else {"is_manager": False}
        ),
    )
    facts.facts = replace(FACTS, groups=tuple(groups))
    with pytest.raises(AccessDeniedError):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert idem.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "missing-new",
        "foreign-new",
        "missing-current",
        "omitted-observation",
        "duplicate-observation",
        "unavailable",
        "incoherent-manager",
    ],
)
async def test_missing_foreign_or_unavailable_facts_never_become_unconfigured(
    setup: Setup, kind: str
) -> None:
    service, facts, _, idem, _, _ = setup
    expected: type[Exception] = DependencyUnavailableError
    match kind:
        case "missing-new":
            facts.facts = replace(
                FACTS, groups=(FACTS.groups[0], replace(FACTS.groups[1], project_id=None))
            )
            expected = ResourceNotFoundError
        case "foreign-new":
            facts.facts = replace(
                FACTS,
                groups=(
                    FACTS.groups[0],
                    replace(FACTS.groups[1], project_id=ProjectId(UUID(int=999))),
                ),
            )
            expected = ResourceNotFoundError
        case "missing-current":
            facts.facts = replace(
                FACTS, groups=(replace(FACTS.groups[0], project_id=None), FACTS.groups[1])
            )
        case "omitted-observation":
            facts.facts = replace(FACTS, groups=FACTS.groups[:1])
        case "duplicate-observation":
            facts.facts = replace(FACTS, groups=FACTS.groups + FACTS.groups[:1])
        case "incoherent-manager":
            facts.facts = replace(
                FACTS, groups=(replace(FACTS.groups[0], is_member=False), FACTS.groups[1])
            )
        case _:
            facts.error = DependencyUnavailableError()
    with pytest.raises(expected):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert idem.calls == 0


@pytest.mark.asyncio
async def test_original_a_to_b_after_current_c_needs_c_and_b_but_not_a(setup: Setup) -> None:
    service, facts, repo, idem, _, events = setup
    facts.facts = replace(
        FACTS,
        access_revision=10,
        audience=UploadAudience((C,)),
        groups=(
            UploadDefaultGroupFactsDTO(B, PROJECT_ID, True, True, False),
            UploadDefaultGroupFactsDTO(C, PROJECT_ID, True, True, False),
        ),
    )
    idem.result = SAVED_RESULT
    result = await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.default.audience == NEW
    assert result.default.access_revision == 8
    assert result.operation == SAVED_RESULT
    assert repo.saved == []
    assert "load" not in events
    assert events.index("lock-current") < events.index("original")
    assert events[-1] == "commit-confirmed"


@pytest.mark.asyncio
@pytest.mark.parametrize("lost", [B, C])
async def test_loss_of_current_c_or_original_destination_b_denies_replay(
    setup: Setup, lost: object
) -> None:
    service, facts, _, idem, _, events = setup
    facts.facts = replace(
        FACTS,
        access_revision=10,
        audience=UploadAudience((C,)),
        groups=tuple(
            UploadDefaultGroupFactsDTO(g, PROJECT_ID, True, g != lost, False) for g in (B, C)
        ),
    )
    idem.result = SAVED_RESULT
    with pytest.raises(AccessDeniedError):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert "original" not in events


@pytest.mark.asyncio
@pytest.mark.parametrize("stale", [False, True])
async def test_fresh_same_set_checks_review_before_noop(setup: Setup, stale: bool) -> None:
    service, facts, repo, _, _, _ = setup
    facts.facts = replace(FACTS, audience=NEW, groups=FACTS.groups[1:])
    repo.default = ProjectUploadDefault(
        organization_id=ORGANIZATION_ID, project_id=PROJECT_ID, audience=NEW, access_revision=7
    )
    command = replace(COMMAND, expected_access_revision=6) if stale else COMMAND
    if stale:
        with pytest.raises(StaleRevisionError):
            await service.set(access=ACCESS, command=command, context=CONTEXT)
        assert not repo.saved
    else:
        result = await service.set(access=ACCESS, command=command, context=CONTEXT)
        assert result.default.access_revision == 7
        assert repo.saved[0].before_audience == repo.saved[0].audience == NEW
        assert repo.saved[0].before_revision == repo.saved[0].access_revision == 7


@pytest.mark.asyncio
async def test_first_configuration_uses_reviewed_project_revision(setup: Setup) -> None:
    service, facts, repo, _, _, _ = setup
    facts.facts = replace(FACTS, audience=None, groups=FACTS.groups[1:])
    repo.default = ProjectUploadDefault(
        organization_id=ORGANIZATION_ID, project_id=PROJECT_ID, audience=None, access_revision=7
    )
    result = await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.default.audience == NEW
    assert repo.saved[0].before_audience is None
    assert repo.saved[0].access_revision == 8


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["save", "completion", "commit-ack"])
async def test_failure_never_causes_automatic_redispatch(setup: Setup, where: str) -> None:
    service, _, repo, idem, tx, events = setup
    error = RuntimeError("controlled failure")
    if where == "save":
        repo.error = error
    elif where == "completion":
        idem.completion_error = error
    else:
        tx.commit_ack_error = error
    with pytest.raises(RuntimeError) as raised:
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert raised.value is error
    assert idem.calls == 1
    if where == "commit-ack":
        assert events[-1] == "commit-outcome-unknown"
        assert "rollback-requested" not in events
    else:
        assert events[-1] == "rollback-requested"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad",
    [
        "missing",
        "before-revision",
        "after-revision",
        "after-audience",
        "actor",
        "operation",
        "project",
    ],
)
async def test_incoherent_history_is_never_returned(setup: Setup, bad: str) -> None:
    service, _, repo, idem, _, _ = setup
    idem.result = SAVED_RESULT
    match bad:
        case "missing":
            repo.saved_original = None
        case "before-revision":
            repo.saved_original = replace(ORIGINAL, before_revision=6)
        case "after-revision":
            repo.saved_original = replace(ORIGINAL, access_revision=9)
        case "after-audience":
            repo.saved_original = replace(ORIGINAL, audience=OLD)
        case "actor":
            repo.saved_original = replace(
                ORIGINAL, actor_principal_id=replace(ACCESS.actor_principal_id, value=UUID(int=999))
            )
        case "operation":
            repo.saved_original = replace(ORIGINAL, operation_id=OperationId("other"))
        case _:
            repo.saved_original = replace(ORIGINAL, project_id=ProjectId(UUID(int=999)))
    with pytest.raises(ConflictError):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["actor", "project", "organization"])
async def test_substituted_scope_is_an_internal_failure(setup: Setup, bad: str) -> None:
    service, facts, _, idem, _, _ = setup
    if bad == "actor":
        facts.facts = replace(
            FACTS,
            action=replace(
                FACTS.action,
                principal=replace(
                    FACTS.action.principal,
                    id=replace(ACCESS.actor_principal_id, value=UUID(int=999)),
                ),
            ),
        )
    elif bad == "project":
        facts.facts = replace(FACTS, project_id=ProjectId(UUID(int=999)))
    else:
        facts.facts = replace(FACTS, organization_id=replace(ORGANIZATION_ID, value=UUID(int=999)))
    with pytest.raises(RuntimeError, match="scope"):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert idem.calls == 0


@pytest.mark.asyncio
async def test_verified_application_is_denied_at_human_only_operation(setup: Setup) -> None:
    service, facts, _, idem, _, _ = setup
    access = AccessContextDTO(
        ACCESS.actor_principal_id, MockAuthenticationEvidence.application_key()
    )
    facts.facts = replace(
        FACTS,
        action=replace(
            FACTS.action, principal=replace(FACTS.action.principal, kind=PrincipalKind.APPLICATION)
        ),
    )
    with pytest.raises(AccessDeniedError):
        await service.set(access=access, command=COMMAND, context=CONTEXT)
    assert idem.calls == 0


@pytest.mark.asyncio
async def test_stale_human_credential_denies_before_history(setup: Setup) -> None:
    service, facts, _, idem, _, _ = setup
    access = AccessContextDTO(ACCESS.actor_principal_id, MockAuthenticationEvidence.human_oauth())
    facts.facts = replace(
        FACTS,
        action=replace(
            FACTS.action,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(2)),
        ),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await service.set(access=access, command=COMMAND, context=CONTEXT)
    assert idem.calls == 0


@pytest.mark.asyncio
async def test_overflow_rejects_before_persistence(setup: Setup) -> None:
    service, facts, repo, _, _, _ = setup
    maximum = 9007199254740991
    facts.facts = replace(FACTS, access_revision=maximum)
    repo.default = ProjectUploadDefault(
        organization_id=ORGANIZATION_ID,
        project_id=PROJECT_ID,
        audience=OLD,
        access_revision=maximum,
    )
    with pytest.raises(ConflictError):
        await service.set(
            access=ACCESS,
            command=replace(COMMAND, expected_access_revision=maximum),
            context=CONTEXT,
        )
    assert not repo.saved


@pytest.mark.parametrize("revision", [-1, 9007199254740992, True])
def test_admission_projection_cannot_carry_an_invalid_revision(revision: int) -> None:
    with pytest.raises((ValueError, TypeError)):
        ProjectUploadAudienceDTO(ORGANIZATION_ID, PROJECT_ID, revision, NEW)


def test_unconfigured_projection_carries_no_administrative_permission() -> None:
    observation = ProjectUploadAudienceDTO(ORGANIZATION_ID, PROJECT_ID, 7, None)
    assert observation.audience is None
    assert observation.access_revision == 7


@pytest.mark.asyncio
async def test_retained_group_management_cannot_be_bypassed_by_new_destination(
    setup: Setup,
) -> None:
    service, facts, _, idem, _, _ = setup
    facts.facts = replace(
        FACTS, groups=(replace(FACTS.groups[0], is_manager=False), FACTS.groups[1])
    )
    with pytest.raises(AccessDeniedError):
        await service.set(
            access=ACCESS,
            command=replace(COMMAND, audience=UploadAudience((A, B))),
            context=CONTEXT,
        )
    assert idem.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_get_checks_authority_before_unconfigured_result(setup: Setup, missing: bool) -> None:
    service, facts, _, idem, _, _ = setup
    facts.facts = (
        None
        if missing
        else replace(
            FACTS,
            audience=None,
            groups=(),
            action=replace(FACTS.action, has_exact_action_grant=False),
        )
    )
    with pytest.raises(ResourceNotFoundError if missing else AccessDeniedError):
        await service.get(access=ACCESS, query=GetProjectUploadDefaultQuery(PROJECT_ID))
    assert idem.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["method", "route"])
async def test_retry_context_cannot_select_a_different_operation(setup: Setup, bad: str) -> None:
    service, _, _, _, _, events = setup
    context = (
        replace(CONTEXT, method=HttpMethod.POST)
        if bad == "method"
        else replace(CONTEXT, requested_route="/v1/projects/other/upload-defaults")
    )
    with pytest.raises(RuntimeError, match="method or route"):
        await service.set(access=ACCESS, command=COMMAND, context=context)
    assert events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["revision", "audience", "project"])
async def test_changed_repository_snapshot_cannot_replace_a_different_default(
    setup: Setup, bad: str
) -> None:
    service, _, repo, _, _, _ = setup
    repo.default = ProjectUploadDefault(
        organization_id=ORGANIZATION_ID,
        project_id=ProjectId(UUID(int=999)) if bad == "project" else PROJECT_ID,
        audience=NEW if bad == "audience" else OLD,
        access_revision=8 if bad == "revision" else 7,
    )
    with pytest.raises(RuntimeError, match="snapshot"):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not repo.saved


@pytest.mark.asyncio
@pytest.mark.parametrize("wrong_id", [False, True])
async def test_completion_must_retain_safe_original_identity(setup: Setup, wrong_id: bool) -> None:
    from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind

    service, _, _, idem, _, events = setup
    idem.completed_result = (
        replace(SAVED_RESULT, operation_id=OperationId("different"))
        if wrong_id
        else replace(SAVED_RESULT, replay_kind=OperationReplayKind.ISSUED_SECRET)
    )
    with pytest.raises(ConflictError):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert events[-1] == "rollback-requested"


@pytest.mark.asyncio
@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize(
    ("member", "manager", "grant", "expected"),
    [
        (False, False, False, ResourceNotFoundError),
        (True, False, False, AccessDeniedError),
        (False, True, False, DependencyUnavailableError),
        (False, False, True, AccessDeniedError),
    ],
    ids=["hidden", "member-only", "manager-only", "action-only"],
)
async def test_proposed_visibility_is_distinct_from_management_before_original(
    setup: Setup,
    replay: bool,
    member: bool,
    manager: bool,
    grant: bool,
    expected: type[Exception],
) -> None:
    service, facts, repo, idem, _, events = setup
    facts.facts = replace(
        FACTS,
        groups=(FACTS.groups[0], UploadDefaultGroupFactsDTO(B, PROJECT_ID, member, manager, grant)),
    )
    idem.result = SAVED_RESULT if replay else NEW_RESERVATION
    with pytest.raises(expected):
        await service.set(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert idem.calls == 0 and repo.saved == []
    assert repo.saved_original == ORIGINAL
    assert events == ["begin", "lock-current", "rollback-requested"]


@pytest.mark.asyncio
@pytest.mark.parametrize("concealed", ["hidden", "missing", "foreign"])
@pytest.mark.parametrize("denied_lower", [False, True])
async def test_all_proposed_visibility_precedes_any_management_denial(
    setup: Setup, concealed: str, denied_lower: bool
) -> None:
    service, facts, repo, idem, _, events = setup
    denied, hidden = (B, C) if denied_lower else (C, B)
    hidden_project = (
        None
        if concealed == "missing"
        else ProjectId(UUID(int=999))
        if concealed == "foreign"
        else PROJECT_ID
    )
    observations = [
        FACTS.groups[0],
        UploadDefaultGroupFactsDTO(denied, PROJECT_ID, True, False, False),
        UploadDefaultGroupFactsDTO(hidden, hidden_project, False, False, False),
    ]
    facts.facts = replace(
        FACTS, groups=tuple(sorted(observations, key=lambda group: group.group_id.value))
    )
    with pytest.raises(ResourceNotFoundError):
        await service.set(
            access=ACCESS,
            command=replace(COMMAND, audience=UploadAudience((B, C))),
            context=CONTEXT,
        )
    assert idem.calls == 0 and repo.saved == []
    assert events == ["begin", "lock-current", "rollback-requested"]


@pytest.mark.asyncio
@pytest.mark.parametrize("replay", [False, True])
@pytest.mark.parametrize("current_state", ["unmanaged", "missing", "incoherent"])
async def test_current_audience_gate_precedes_hidden_proposals_and_history(
    setup: Setup, replay: bool, current_state: str
) -> None:
    service, facts, repo, idem, _, events = setup
    current = UploadDefaultGroupFactsDTO(
        C,
        None if current_state == "missing" else PROJECT_ID,
        current_state != "incoherent",
        current_state == "incoherent",
        False,
    )
    facts.facts = replace(
        FACTS,
        audience=UploadAudience((C,)),
        groups=(UploadDefaultGroupFactsDTO(A, None, False, False, False), current),
    )
    idem.result = SAVED_RESULT if replay else NEW_RESERVATION
    expected = AccessDeniedError if current_state == "unmanaged" else DependencyUnavailableError
    with pytest.raises(expected):
        await service.set(access=ACCESS, command=replace(COMMAND, audience=OLD), context=CONTEXT)
    assert idem.calls == 0 and repo.saved == []
    assert repo.saved_original == ORIGINAL
    assert events == ["begin", "lock-current", "rollback-requested"]
