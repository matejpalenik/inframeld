from dataclasses import replace

import pytest
from tests.support.mock_human_lifecycle import (
    ACCESS,
    IDENTITY,
    RESTORE,
    SYNC,
    VERSION,
    MockHumanLifecycle,
    context,
)

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@pytest.mark.asyncio
async def test_restore_verifies_outside_sql_and_advances_once_with_the_local_transition() -> None:
    fixture = MockHumanLifecycle(restoring=True)
    result = await fixture.restore_service().restore(
        access=ACCESS, command=RESTORE, context=context(True)
    )
    assert result.access_revision == 8 and result.credential_version == HumanCredentialVersion(6)
    assert len(fixture.committed) == 1 and fixture.committed[0][1].status is PrincipalStatus.ACTIVE
    assert fixture.committed[0][2] == HumanCredentialVersion(6)
    assert fixture.events.index("verify") > fixture.events.index("commit")
    assert (
        fixture.events.index("verify")
        < fixture.events.index("identity-org-fresh")
        < fixture.events.index("reserve")
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("restriction", ["cleanup", "newer-recovery", "missing-version", "retired"])
async def test_restoration_requires_original_cleanup_and_current_restrictions(
    restriction: str,
) -> None:
    fixture = MockHumanLifecycle(restoring=True)
    assert fixture.facts is not None and fixture.facts.target is not None
    if restriction == "cleanup":
        fixture.facts = replace(fixture.facts, required_cleanup_confirmed=False)
    elif restriction == "newer-recovery":
        fixture.facts = replace(fixture.facts, has_newer_recovery_block=True)
    elif restriction == "missing-version":
        fixture.facts = replace(fixture.facts, target_version=None)
    else:
        fixture.facts = replace(
            fixture.facts, target=replace(fixture.facts.target, status=PrincipalStatus.RETIRED)
        )
    with pytest.raises(
        DependencyUnavailableError if restriction == "missing-version" else ConflictError
    ):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert not fixture.writes and not fixture.committed


@pytest.mark.asyncio
@pytest.mark.parametrize("denial", ["action", "recovery", "stale"])
async def test_restore_denial_precedes_provider_originals_and_effects(denial: str) -> None:
    fixture = MockHumanLifecycle(restoring=True)
    assert fixture.facts is not None and fixture.facts.actor_credential_facts is not None
    fixture.facts = replace(
        fixture.facts,
        actor_has_action=denial != "action",
        actor_has_pending_recovery=denial == "recovery",
        actor_credential_facts=replace(
            fixture.facts.actor_credential_facts, binding_matches_actor=denial != "stale"
        ),
    )
    fixture.replay = SYNC
    with pytest.raises(AuthenticationRequiredError if denial == "stale" else AccessDeniedError):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert "verify" not in fixture.events and "reserve" not in fixture.events and not fixture.writes


@pytest.mark.asyncio
async def test_restoration_replay_is_historical_without_reactivating_later_suspension() -> None:
    fixture = MockHumanLifecycle(restoring=True)
    first = await fixture.restore_service().restore(
        access=ACCESS, command=RESTORE, context=context(True)
    )
    fixture.replay = SYNC
    fixture.writes.clear()
    fixture.committed.clear()
    assert fixture.facts is not None
    fixture.facts = replace(
        fixture.facts,
        access_revision=88,
        target_version=HumanCredentialVersion(9),
        required_cleanup_confirmed=False,
        has_newer_recovery_block=True,
    )
    result = await fixture.restore_service().restore(
        access=ACCESS, command=RESTORE, context=context(True)
    )
    assert (
        result.credential_version == first.credential_version
        and result.access_revision == first.access_revision
    )
    assert result.operation == SYNC and not fixture.writes


@pytest.mark.asyncio
async def test_an_active_noop_does_not_advance_the_version_or_revision() -> None:
    fixture = MockHumanLifecycle(restoring=True)
    assert fixture.facts is not None and fixture.facts.target is not None
    fixture.facts = replace(
        fixture.facts, target=replace(fixture.facts.target, status=PrincipalStatus.ACTIVE)
    )
    result = await fixture.restore_service().restore(
        access=ACCESS, command=RESTORE, context=context(True)
    )
    assert result.credential_version == VERSION and result.access_revision == 7


@pytest.mark.asyncio
async def test_fresh_stale_revision_precedes_active_noop() -> None:
    fixture = MockHumanLifecycle(restoring=True)
    assert fixture.facts is not None and fixture.facts.target is not None
    fixture.facts = replace(
        fixture.facts,
        access_revision=8,
        target=replace(fixture.facts.target, status=PrincipalStatus.ACTIVE),
    )
    with pytest.raises(StaleRevisionError):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert not fixture.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("overflow", ["revision", "version"])
async def test_transition_never_resets_or_overflows_security_history(overflow: str) -> None:
    fixture = MockHumanLifecycle(restoring=True)
    assert fixture.facts is not None
    if overflow == "revision":
        fixture.facts = replace(fixture.facts, access_revision=RevisionValidation.MAX_VALUE)
        command = replace(RESTORE, expected_access_revision=RevisionValidation.MAX_VALUE)
    else:
        fixture.facts = replace(fixture.facts, target_version=HumanCredentialVersion(2**63 - 1))
        command = RESTORE
    with pytest.raises(ConflictError):
        await fixture.restore_service().restore(
            access=ACCESS, command=command, context=context(True)
        )
    assert not fixture.writes


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["missing", "wrong", "unavailable"])
async def test_current_stable_provider_identity_cannot_be_replaced(provider: str) -> None:
    fixture = MockHumanLifecycle(restoring=True)
    if provider == "missing":
        fixture.provider_missing = True
    elif provider == "wrong":
        from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject

        fixture.provider_identity = replace(IDENTITY, subject=IdentitySubject("other"))
    else:
        fixture.provider_error = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError if provider == "unavailable" else ConflictError):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert "reserve" not in fixture.events and not fixture.writes


@pytest.mark.asyncio
async def test_fresh_locked_authority_is_rechecked_after_provider_work() -> None:
    fixture = MockHumanLifecycle(restoring=True)
    assert fixture.facts is not None
    fixture.final_facts = replace(fixture.facts, actor_has_action=False)
    with pytest.raises(AccessDeniedError):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert "verify" in fixture.events and "reserve" not in fixture.events


@pytest.mark.asyncio
async def test_restoration_audit_receives_the_exact_security_review_reference() -> None:
    fixture = MockHumanLifecycle(restoring=True)
    await fixture.restore_service().restore(access=ACCESS, command=RESTORE, context=context(True))
    assert fixture.restoration_command == RESTORE


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["save", "completion", "unknown-commit", "cancel"])
async def test_restoration_failures_do_not_invent_a_rollback_after_unknown_commit(
    failure: str,
) -> None:
    import asyncio

    fixture = MockHumanLifecycle(restoring=True)
    if failure == "save":
        fixture.save_error = DependencyUnavailableError()
    elif failure == "completion":
        fixture.completion_error = DependencyUnavailableError()
    elif failure == "cancel":
        fixture.save_error = asyncio.CancelledError()
    else:
        fixture.commit_unknown = True
    with pytest.raises(
        asyncio.CancelledError if failure == "cancel" else DependencyUnavailableError
    ):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert fixture.events.count("verify") == 1 and fixture.events.count("reserve") == 1
    if failure == "unknown-commit":
        assert len(fixture.committed) == 1 and fixture.events[-1] == "commit-unknown"
    else:
        assert not fixture.committed and fixture.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_provider_observation_cannot_authorize_a_changed_local_identity_link() -> None:
    from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject

    fixture = MockHumanLifecycle(restoring=True)
    assert fixture.facts is not None
    fixture.final_facts = replace(
        fixture.facts, target_identity=replace(IDENTITY, subject=IdentitySubject("changed"))
    )
    with pytest.raises(ConflictError):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert "reserve" not in fixture.events and not fixture.writes


@pytest.mark.asyncio
async def test_missing_restoration_original_never_reapplies_the_transition() -> None:
    fixture = MockHumanLifecycle(restoring=True)
    fixture.replay = SYNC
    with pytest.raises(ConflictError):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert not fixture.writes


@pytest.mark.asyncio
async def test_corrupt_original_revision_cannot_be_returned_as_a_safe_receipt() -> None:
    fixture = MockHumanLifecycle(restoring=True)
    original = await fixture.restore_service().restore(
        access=ACCESS, command=RESTORE, context=context(True)
    )
    fixture.restoration_result = replace(original, access_revision=2**53)
    fixture.replay = SYNC
    fixture.writes.clear()
    with pytest.raises(ConflictError):
        await fixture.restore_service().restore(
            access=ACCESS, command=RESTORE, context=context(True)
        )
    assert not fixture.writes
