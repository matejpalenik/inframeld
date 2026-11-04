import asyncio
from dataclasses import replace
from typing import Literal, cast
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import SAVED_RESULT
from tests.support.project_membership_change_scenarios import (
    ACCESS,
    ADD,
    ADD_CONTEXT,
    ALICE,
    BOB,
    FACTS,
    PROJECT,
    REMOVE,
    REMOVE_CONTEXT,
    MembershipChangeScenario,
)

from inframeld_backend.access.application.commands.add_project_member_command import (
    AddProjectMemberCommand,
)
from inframeld_backend.access.application.commands.remove_project_member_command import (
    RemoveProjectMemberCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_departure_candidate_dto import (
    ProjectDepartureCandidateDTO,
)
from inframeld_backend.access.application.dtos.project_departure_responsibility_dto import (
    ProjectDepartureResponsibilityDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)


@pytest.mark.parametrize("command", [ADD, REMOVE], ids=["add", "remove"])
@pytest.mark.parametrize(
    "revision,error",
    [
        (True, TypeError),
        (False, TypeError),
        (0.0, TypeError),
        (1.5, TypeError),
        ("7", TypeError),
        (None, TypeError),
        (-1, ValueError),
        (2**63, ValueError),
    ],
)
def test_commands_reject_noninteger_or_out_of_range_reviewed_revision(
    command: AddProjectMemberCommand | RemoveProjectMemberCommand,
    revision: object,
    error: type[Exception],
) -> None:
    with pytest.raises(error):
        replace(command, expected_access_revision=cast(int, revision))


@pytest.mark.parametrize("command", [ADD, REMOVE], ids=["add", "remove"])
@pytest.mark.parametrize("revision", [0, 2**63 - 1])
def test_commands_accept_exact_integer_revision_boundaries(
    command: AddProjectMemberCommand | RemoveProjectMemberCommand, revision: int
) -> None:
    assert replace(command, expected_access_revision=revision).expected_access_revision == revision


def test_fingerprint_preserves_method_recipient_project_and_reviewed_revision() -> None:
    s = MembershipChangeScenario()
    original = s.fingerprints.for_add(ADD)
    assert s.fingerprints.for_add(ADD) == original
    assert s.fingerprints.for_remove(REMOVE) != original
    assert s.fingerprints.for_add(replace(ADD, principal_id=ALICE.id)) != original
    assert s.fingerprints.for_add(replace(ADD, project_id=ProjectId(UUID(int=99)))) != original
    assert s.fingerprints.for_add(replace(ADD, expected_access_revision=8)) != original


@pytest.mark.asyncio
async def test_oauth_generation_loss_blocks_replay_before_reservation() -> None:
    s = MembershipChangeScenario()
    access = AccessContextDTO(ALICE.id, MockAuthenticationEvidence.human_oauth())
    s.idempotency.result = SAVED_RESULT
    s.facts.facts = replace(
        FACTS,
        action=replace(
            FACTS.action,
            oauth_credential_facts=HumanOAuthCredentialFactsDTO(True, HumanCredentialVersion(2)),
        ),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await s.service.add_member(access=access, command=ADD, context=ADD_CONTEXT)
    assert "reserve" not in s.events and s.writer.saved is None and s.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("member", [False, True])
async def test_removing_an_inactive_human_does_not_require_restoring_the_account(
    member: bool,
) -> None:
    s = MembershipChangeScenario()
    s.facts.facts = replace(
        FACTS,
        recipient=replace(BOB, status=PrincipalStatus.SUSPENDED),
        recipient_has_pending_recovery=True,
        recipient_is_project_member=member,
    )
    result = await s.service.remove_member(access=ACCESS, command=REMOVE, context=REMOVE_CONTEXT)
    assert result.status_code == 200 and result.changed is member
    assert result.access_revision == 7 + int(member)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "context",
    [
        replace(ADD_CONTEXT, method="DELETE"),
        replace(ADD_CONTEXT, requested_route="/v1/projects/another/members/another"),
    ],
)
async def test_operation_context_cannot_replace_the_method_or_concrete_target(
    context: OperationAdmissionContextDTO,
) -> None:
    s = MembershipChangeScenario()
    with pytest.raises(RuntimeError):
        await s.service.add_member(access=ACCESS, command=ADD, context=context)
    assert s.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("target_kind", ["project", "access_group", "application_account"])
async def test_unsupported_stored_action_cannot_count_as_remaining_authority(
    target_kind: Literal["project", "access_group", "application_account"],
) -> None:
    s = MembershipChangeScenario()
    candidate = ProjectDepartureCandidateDTO(ALICE, False, True, True, True, False, False)
    responsibility = ProjectDepartureResponsibilityDTO(
        target_kind, PROJECT.value, ActionId("unsupported-action"), False, False, (candidate,)
    )
    s.facts.facts = replace(
        FACTS, recipient_is_project_member=True, responsibilities=(responsibility,)
    )
    with pytest.raises(ConflictError):
        await s.service.remove_member(access=ACCESS, command=REMOVE, context=REMOVE_CONTEXT)
    assert s.writer.saved is None and s.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_departure_facts_cannot_substitute_another_project_responsibility() -> None:
    s = MembershipChangeScenario()
    candidate = ProjectDepartureCandidateDTO(ALICE, False, True, True, True, False, False)
    responsibility = ProjectDepartureResponsibilityDTO(
        "project", UUID(int=99), ActionId("manage-project-members"), False, False, (candidate,)
    )
    s.facts.facts = replace(
        FACTS, recipient_is_project_member=True, responsibilities=(responsibility,)
    )
    with pytest.raises(RuntimeError):
        await s.service.remove_member(access=ACCESS, command=REMOVE, context=REMOVE_CONTEXT)
    assert s.writer.saved is None and s.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("already", [False, True])
async def test_add_commits_bare_membership_and_original_changed_status(already: bool) -> None:
    s = MembershipChangeScenario()
    if already:
        s.member()
    result = await s.service.add_member(access=ACCESS, command=ADD, context=ADD_CONTEXT)
    assert result.changed is not already
    assert result.status_code == (200 if already else 201)
    assert result.access_revision == (7 if already else 8)
    assert result.principal_id == BOB.id and result.project_id == PROJECT
    assert s.events == ["begin", "facts", "reserve", "save", "complete", "commit"]
    assert s.writer.saved is not None and s.writer.saved[2] == "add"
    assert s.idempotency.lookup_authority is not None
    assert s.idempotency.lookup_authority.action_id == ActionId("manage-project-members")


@pytest.mark.asyncio
@pytest.mark.parametrize("member", [False, True])
async def test_remove_retains_original_changed_result_without_requiring_live_membership(
    member: bool,
) -> None:
    s = MembershipChangeScenario()
    if member:
        s.member()
    result = await s.service.remove_member(access=ACCESS, command=REMOVE, context=REMOVE_CONTEXT)
    assert result.changed is member and result.status_code == 200
    assert result.access_revision == 7 + int(member)
    assert s.writer.saved is not None and s.writer.saved[2] == "remove"


@pytest.mark.asyncio
async def test_replay_returns_original_add_after_later_removal_without_new_write() -> None:
    s = MembershipChangeScenario()
    s.idempotency.result = SAVED_RESULT
    s.facts.facts = replace(
        FACTS, access_revision=50, recipient=replace(BOB, status=PrincipalStatus.SUSPENDED)
    )
    result = await s.service.add_member(access=ACCESS, command=ADD, context=ADD_CONTEXT)
    assert result is s.results.result and result.status_code == 201 and result.access_revision == 8
    assert s.writer.saved is None and s.events == [
        "begin",
        "facts",
        "reserve",
        "original",
        "commit",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["missing", "authority", "membership", "suspended", "recovery"])
async def test_current_actor_authority_precedes_reservation_and_business_replay(
    denial: str,
) -> None:
    s = MembershipChangeScenario()
    s.idempotency.result = SAVED_RESULT
    action = FACTS.action
    if denial == "authority":
        action = replace(action, has_exact_action_grant=False)
    if denial == "membership":
        action = replace(action, is_project_member=False)
    if denial == "suspended":
        action = replace(action, principal=replace(ALICE, status=PrincipalStatus.SUSPENDED))
    if denial == "recovery":
        action = replace(action, has_pending_recovery=True)
    s.facts.facts = None if denial == "missing" else replace(FACTS, action=action)
    with pytest.raises(
        ResourceNotFoundError
        if denial in {"missing", "membership", "suspended"}
        else AccessDeniedError
    ):
        await s.service.add_member(access=ACCESS, command=ADD, context=ADD_CONTEXT)
    assert "reserve" not in s.events and s.writer.saved is None and s.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_stale_new_request_leaves_no_saved_membership() -> None:
    s = MembershipChangeScenario()
    with pytest.raises(StaleRevisionError):
        await s.service.add_member(
            access=ACCESS, command=replace(ADD, expected_access_revision=6), context=ADD_CONTEXT
        )
    assert s.writer.saved is None and s.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["missing", "application", "suspended", "recovery", "identity"])
async def test_new_add_requires_an_eligible_admitted_human(case: str) -> None:
    s = MembershipChangeScenario()
    facts = FACTS
    if case == "missing":
        facts = replace(facts, recipient=None)
    if case == "application":
        facts = replace(facts, recipient=replace(BOB, kind=PrincipalKind.APPLICATION))
    if case == "suspended":
        facts = replace(facts, recipient=replace(BOB, status=PrincipalStatus.SUSPENDED))
    if case == "recovery":
        facts = replace(facts, recipient_has_pending_recovery=True)
    if case == "identity":
        facts = replace(facts, recipient_has_coherent_identity=False)
    s.facts.facts = facts
    with pytest.raises(
        ResourceNotFoundError
        if case == "missing"
        else InvalidInputError
        if case == "application"
        else ConflictError
    ):
        await s.service.add_member(access=ACCESS, command=ADD, context=ADD_CONTEXT)
    assert s.writer.saved is None and s.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_removal_rejects_stranded_exact_responsibility_before_writing() -> None:
    s = MembershipChangeScenario()
    s.facts.facts = replace(
        FACTS,
        recipient_is_project_member=True,
        responsibilities=(
            ProjectDepartureResponsibilityDTO(
                "project", PROJECT.value, ActionId("edit-project-metadata"), False, False, ()
            ),
        ),
    )
    with pytest.raises(ConflictError):
        await s.service.remove_member(access=ACCESS, command=REMOVE, context=REMOVE_CONTEXT)
    assert s.writer.saved is None and "complete" not in s.events and s.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [RuntimeError("save failed"), asyncio.CancelledError()])
async def test_save_failure_or_cancellation_rolls_back_without_completion(
    failure: BaseException,
) -> None:
    s = MembershipChangeScenario()
    s.writer.error = failure
    with pytest.raises(type(failure)):
        await s.service.add_member(access=ACCESS, command=ADD, context=ADD_CONTEXT)
    assert "complete" not in s.events and s.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_wrong_scope_facts_fail_before_reservation() -> None:
    s = MembershipChangeScenario()
    s.facts.facts = replace(FACTS, project_id=ProjectId(UUID(int=99)))
    with pytest.raises(RuntimeError):
        await s.service.add_member(access=ACCESS, command=ADD, context=ADD_CONTEXT)
    assert "reserve" not in s.events and s.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_replay_rejects_changed_original_business_binding() -> None:
    s = MembershipChangeScenario()
    s.idempotency.result = SAVED_RESULT
    s.results.result = replace(s.results.result, principal_id=ALICE.id)
    with pytest.raises(ConflictError):
        await s.service.add_member(access=ACCESS, command=ADD, context=ADD_CONTEXT)
    assert s.writer.saved is None and s.events[-1] == "rollback"
