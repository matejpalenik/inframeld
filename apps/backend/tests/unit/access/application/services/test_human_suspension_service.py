from dataclasses import replace

import pytest
from tests.support.mock_human_lifecycle import (
    ACCESS,
    ASYNC,
    EVIDENCE,
    OPERATION,
    REQUEST_ID,
    SUSPEND,
    TARGET,
    MockHumanLifecycle,
    context,
    suspension,
)

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)


@pytest.mark.asyncio
async def test_suspension_commits_the_local_block_and_original_obligation_before_acknowledgment() -> (
    None
):
    fixture = MockHumanLifecycle()
    result = await fixture.suspend_service().suspend(
        access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
    )
    assert result.access_revision == 8 and result.principal_id == TARGET.id
    assert result.operation.operation_id == OPERATION and result.operation.created
    assert len(fixture.committed) == 1
    kind, target, _original = fixture.committed[0]
    assert kind == "suspend" and target.status is PrincipalStatus.SUSPENDED
    assert "verify" not in fixture.events
    assert (
        fixture.events.index("identity-org-fresh")
        < fixture.events.index("reserve")
        < fixture.events.index("save-suspension")
        < fixture.events.index("complete")
        < fixture.events.index("save-result")
    )
    assert fixture.events[-1] == "commit"


@pytest.mark.asyncio
async def test_self_suspension_has_no_ordinary_handover_prerequisite() -> None:
    fixture = MockHumanLifecycle()
    assert fixture.facts is not None
    fixture.facts = replace(
        fixture.facts, target=fixture.facts.actor, target_identity=EVIDENCE.identity
    )
    command = replace(SUSPEND, principal_id=ACCESS.actor_principal_id)
    request = replace(
        context(),
        requested_route=f"/v1/organizations/{command.organization_id.value}/humans/{command.principal_id.value}/suspend",
    )
    result = await fixture.suspend_service().suspend(
        access=ACCESS, command=command, context=request, request_id=REQUEST_ID
    )
    assert (
        result.principal_id == ACCESS.actor_principal_id
        and fixture.committed[0][1].status is PrincipalStatus.SUSPENDED
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["suspended", "recovery", "action", "stale"])
async def test_current_authority_precedes_original_history_and_any_effect(denial: str) -> None:
    fixture = MockHumanLifecycle()
    assert fixture.facts is not None and fixture.facts.actor_credential_facts is not None
    if denial == "suspended":
        fixture.facts = replace(
            fixture.facts, actor=replace(fixture.facts.actor, status=PrincipalStatus.SUSPENDED)
        )
    elif denial == "recovery":
        fixture.facts = replace(fixture.facts, actor_has_pending_recovery=True)
    elif denial == "action":
        fixture.facts = replace(fixture.facts, actor_has_action=False)
    else:
        fixture.facts = replace(
            fixture.facts,
            actor_credential_facts=replace(
                fixture.facts.actor_credential_facts, binding_matches_actor=False
            ),
        )
    fixture.replay = ASYNC
    with pytest.raises(AuthenticationRequiredError if denial == "stale" else AccessDeniedError):
        await fixture.suspend_service().suspend(
            access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
        )
    assert (
        "reserve" not in fixture.events and "original" not in fixture.events and not fixture.writes
    )


@pytest.mark.asyncio
async def test_original_replay_does_not_repeat_a_later_restored_or_resuspended_account() -> None:
    fixture = MockHumanLifecycle()
    first = await fixture.suspend_service().suspend(
        access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
    )
    fixture.replay = ASYNC
    fixture.writes.clear()
    fixture.committed.clear()
    assert fixture.facts is not None
    fixture.facts = replace(
        fixture.facts,
        access_revision=55,
        current_suspension=suspension(),
        has_newer_recovery_block=True,
    )
    result = await fixture.suspend_service().suspend(
        access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
    )
    assert result.operation == ASYNC and result.cleanup_operation_id == first.cleanup_operation_id
    assert result.access_revision == first.access_revision and not fixture.writes


@pytest.mark.asyncio
async def test_fresh_stale_revision_fails_before_a_noop_or_replacement_obligation() -> None:
    fixture = MockHumanLifecycle()
    assert fixture.facts is not None
    fixture.facts = replace(
        fixture.facts,
        access_revision=8,
        target=replace(TARGET, status=PrincipalStatus.SUSPENDED),
        current_suspension=suspension(),
    )
    with pytest.raises(StaleRevisionError):
        await fixture.suspend_service().suspend(
            access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
        )
    assert not fixture.writes and not fixture.committed


@pytest.mark.asyncio
async def test_fresh_already_suspended_request_keeps_the_original_cleanup_and_revision() -> None:
    fixture = MockHumanLifecycle()
    assert fixture.facts is not None
    original = suspension()
    fixture.facts = replace(
        fixture.facts,
        target=replace(TARGET, status=PrincipalStatus.SUSPENDED),
        current_suspension=original,
    )
    result = await fixture.suspend_service().suspend(
        access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
    )
    assert result.access_revision == 7 and fixture.committed[0][2] is original


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["save", "completion", "unknown-commit"])
async def test_local_failure_and_unknown_commit_never_dispatch_or_repeat(failure: str) -> None:
    fixture = MockHumanLifecycle()
    error = DependencyUnavailableError()
    if failure == "save":
        fixture.save_error = error
    elif failure == "completion":
        fixture.completion_error = error
    else:
        fixture.commit_unknown = True
    with pytest.raises(DependencyUnavailableError):
        await fixture.suspend_service().suspend(
            access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
        )
    assert fixture.events.count("reserve") == 1 and "verify" not in fixture.events
    if failure == "unknown-commit":
        assert len(fixture.committed) == 1 and fixture.events[-1] == "commit-unknown"
    else:
        assert not fixture.committed and fixture.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_missing_original_cannot_redispatch_suspension() -> None:
    fixture = MockHumanLifecycle()
    fixture.replay = ASYNC
    with pytest.raises(ConflictError):
        await fixture.suspend_service().suspend(
            access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
        )
    assert not fixture.writes


@pytest.mark.asyncio
async def test_suspension_audit_receives_the_exact_reviewed_reason() -> None:
    fixture = MockHumanLifecycle()
    await fixture.suspend_service().suspend(
        access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
    )
    assert fixture.suspension_command == SUSPEND


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["facts", "target", "identity"])
async def test_missing_required_target_facts_never_reserve_or_block_another_identity(
    missing: str,
) -> None:
    from inframeld_backend.shared.application.errors.application_errors import ResourceNotFoundError

    fixture = MockHumanLifecycle()
    assert fixture.facts is not None
    if missing == "facts":
        fixture.facts = None
    elif missing == "target":
        fixture.facts = replace(fixture.facts, target=None)
    else:
        fixture.facts = replace(fixture.facts, target_identity=None)
    with pytest.raises(
        DependencyUnavailableError if missing == "identity" else ResourceNotFoundError
    ):
        await fixture.suspend_service().suspend(
            access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
        )
    assert "reserve" not in fixture.events and not fixture.writes


@pytest.mark.asyncio
async def test_a_foreign_retained_original_does_not_change_or_disclose_another_target() -> None:
    from uuid import UUID

    from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId

    fixture = MockHumanLifecycle()
    original = await fixture.suspend_service().suspend(
        access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
    )
    fixture.suspension_result = replace(original, principal_id=PrincipalId(UUID(int=999)))
    fixture.replay = ASYNC
    fixture.writes.clear()
    with pytest.raises(ConflictError):
        await fixture.suspend_service().suspend(
            access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
        )
    assert not fixture.writes


@pytest.mark.asyncio
async def test_corrupt_original_revision_cannot_be_returned_as_a_safe_receipt() -> None:
    fixture = MockHumanLifecycle()
    original = await fixture.suspend_service().suspend(
        access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
    )
    fixture.suspension_result = replace(original, access_revision=2**53)
    fixture.replay = ASYNC
    fixture.writes.clear()
    with pytest.raises(ConflictError):
        await fixture.suspend_service().suspend(
            access=ACCESS, command=SUSPEND, context=context(), request_id=REQUEST_ID
        )
    assert not fixture.writes
