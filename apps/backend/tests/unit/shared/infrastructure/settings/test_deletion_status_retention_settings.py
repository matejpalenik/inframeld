"""Reject malformed installation policy before a binding can capture it."""

import pytest
from pydantic import ValidationError

from inframeld_backend.shared.infrastructure.settings.deletion_status_retention_settings import (
    DeletionStatusRetentionSettings,
)


@pytest.mark.parametrize("days", [1, 7, 29, 30, 90])
def test_capture_selected_profile_without_a_retention_clock(days: int) -> None:
    profile = DeletionStatusRetentionSettings(days=days).to_profile()
    assert profile.days == days
    assert profile.policy_version == "ADR-0117/PD-KNOWLEDGE-02:v1"


def test_absent_setting_uses_thirty_day_profile() -> None:
    assert DeletionStatusRetentionSettings().to_profile().days == 30


@pytest.mark.parametrize("days", [None, True, False, 0, -1, 91, 30.5, "30.5", "unknown"])
def test_reject_invalid_or_unsupported_retention(days: object) -> None:
    with pytest.raises(ValidationError):
        DeletionStatusRetentionSettings.model_validate({"days": days})
