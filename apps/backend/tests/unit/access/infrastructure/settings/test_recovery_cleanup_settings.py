import pytest
from pydantic import ValidationError

from inframeld_backend.access.infrastructure.settings.recovery_cleanup_settings import (
    RecoveryCleanupSettings,
)


def test_recovery_defaults_need_no_browser_callback_or_fingerprint_configuration() -> None:
    settings = RecoveryCleanupSettings.model_validate(
        {"authority": "kratos:local", "hydra_admin_url": "http://hydra:4445"}
    )
    assert (
        settings.poll_seconds,
        settings.provider_timeout_seconds,
        settings.database_timeout_seconds,
        settings.lease_seconds,
        settings.shutdown_seconds,
    ) == (1, 5, 5, 60, 15)


@pytest.mark.parametrize(
    "field",
    [
        "poll_seconds",
        "provider_timeout_seconds",
        "database_timeout_seconds",
        "lease_seconds",
        "shutdown_seconds",
    ],
)
@pytest.mark.parametrize("value", [True, 0, -1, float("inf"), float("nan")])
def test_invalid_worker_deadlines_fail_before_any_io(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        RecoveryCleanupSettings.model_validate(
            {"authority": "kratos:local", "hydra_admin_url": "http://hydra:4445", field: value}
        )


def test_claim_lifetime_must_cover_the_bounded_fixed_steps_and_checkpoints() -> None:
    with pytest.raises(ValidationError):
        RecoveryCleanupSettings.model_validate(
            {
                "authority": "kratos:local",
                "hydra_admin_url": "http://hydra:4445",
                "lease_seconds": 5,
            }
        )
