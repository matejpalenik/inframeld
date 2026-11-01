"""Capture approved bounds without accepting a new retention clock or policy reset."""

from typing import cast

import pytest

from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)


def test_default_and_operator_maximum_are_captured_exactly() -> None:
    assert DeletionStatusRetentionProfile().days == 30
    assert DeletionStatusRetentionProfile(90).days == 90
    assert DeletionStatusRetentionProfile().policy_version == "ADR-0117/PD-KNOWLEDGE-02:v1"


@pytest.mark.parametrize("days", [1, 7, 29])
def test_explicitly_selected_shorter_profile_is_captured(days: int) -> None:
    assert DeletionStatusRetentionProfile(days).days == days


@pytest.mark.parametrize("days", [0, 91, -1])
def test_nonpositive_or_excessive_period_is_rejected(days: int) -> None:
    with pytest.raises(ValueError):
        DeletionStatusRetentionProfile(days)


@pytest.mark.parametrize("days", [True, False, 30.0, "30", None])
def test_framework_values_require_validation_before_profile_capture(days: object) -> None:
    with pytest.raises(TypeError):
        DeletionStatusRetentionProfile(cast(int, days))


def test_unknown_policy_version_cannot_establish_retention() -> None:
    with pytest.raises(ValueError):
        DeletionStatusRetentionProfile(policy_version="unreviewed-policy")
