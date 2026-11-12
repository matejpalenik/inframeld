from typing import cast
from uuid import UUID

import pytest
from tests.support.mock_human_lifecycle import suspension

from inframeld_backend.access.application.value_objects.security_review_reference import (
    SecurityReviewReference,
)
from inframeld_backend.access.application.value_objects.suspension_reason import SuspensionReason
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.value_objects.human_suspension_id import HumanSuspensionId
from inframeld_backend.shared.domain.errors.domain_errors import InvalidStateTransitionError


@pytest.mark.parametrize("step", ["kratos_sessions", "hydra_cli_grants", "hydra_remembered_logins"])
def test_cleanup_outcomes_are_independent_and_confirmed_is_monotonic(step: str) -> None:
    original = suspension()
    record = getattr(original, "record_" + step)
    record(State.UNCERTAIN)
    assert getattr(original, step) is State.UNCERTAIN
    assert not original.is_cleanup_confirmed
    record(State.CONFIRMED)
    record(State.CONFIRMED)
    with pytest.raises(InvalidStateTransitionError):
        record(State.FAILED)
    assert getattr(original, step) is State.CONFIRMED
    for other in {"kratos_sessions", "hydra_cli_grants", "hydra_remembered_logins"} - {step}:
        assert getattr(original, other) is State.PENDING


@pytest.mark.parametrize("step", ["kratos_sessions", "hydra_cli_grants", "hydra_remembered_logins"])
def test_pending_is_not_cleanup_confirmation(step: str) -> None:
    with pytest.raises(InvalidStateTransitionError):
        getattr(suspension(), "record_" + step)(State.PENDING)


def test_all_three_confirmations_are_needed_and_original_scope_does_not_change() -> None:
    original = suspension()
    identity = (
        original.id,
        original.organization_id,
        original.principal_id,
        original.installation_id,
        original.authority,
        original.subject,
    )
    original.record_kratos_sessions(State.CONFIRMED)
    original.record_hydra_cli_grants(State.CONFIRMED)
    assert not original.is_cleanup_confirmed
    original.record_hydra_remembered_logins(State.CONFIRMED)
    assert original.is_cleanup_confirmed
    assert identity == (
        original.id,
        original.organization_id,
        original.principal_id,
        original.installation_id,
        original.authority,
        original.subject,
    )
    with pytest.raises(AttributeError):
        original.__setattr__("subject", original.subject)


@pytest.mark.parametrize("value", ["", " ", "unsafe\nvalue", "unsafe\x00value", "x" * 1025])
@pytest.mark.parametrize("kind", [SuspensionReason, SecurityReviewReference])
def test_audit_values_are_bounded_single_line_references(
    kind: type[SuspensionReason] | type[SecurityReviewReference], value: str
) -> None:
    with pytest.raises(ValueError):
        kind(value)


@pytest.mark.parametrize("kind", [SuspensionReason, SecurityReviewReference])
def test_safe_audit_text_is_preserved_but_not_rendered(
    kind: type[SuspensionReason] | type[SecurityReviewReference],
) -> None:
    value = kind("security-review/legitimate-person")
    assert value.value == "security-review/legitimate-person"
    assert value.value not in repr(value)


def test_suspension_identifier_requires_a_parsed_uuid() -> None:
    with pytest.raises(TypeError):
        HumanSuspensionId(cast(UUID, "not-a-uuid"))


def test_original_obligation_identity_survives_cleanup_checkpoints() -> None:
    first, second = suspension(), suspension()
    first.record_kratos_sessions(State.CONFIRMED)
    assert first == second and hash(first) == hash(second)


@pytest.mark.parametrize("separator", ["\x85", "\u2028", "\u2029"])
@pytest.mark.parametrize("kind", [SuspensionReason, SecurityReviewReference])
def test_audit_values_reject_unicode_line_separators(
    kind: type[SuspensionReason] | type[SecurityReviewReference], separator: str
) -> None:
    with pytest.raises(ValueError):
        kind("review" + separator + "another-line")
