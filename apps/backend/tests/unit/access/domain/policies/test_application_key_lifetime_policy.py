"""Reject impossible fresh expiries before a secret or database effect exists."""

from datetime import UTC, datetime, timedelta, timezone

import pytest

from inframeld_backend.access.domain.policies.application_key_lifetime_policy import (
    ApplicationKeyLifetimePolicy,
)

ISSUED = datetime(2026, 11, 8, 10, 12, 13, 123456, tzinfo=UTC)


@pytest.mark.parametrize("seconds", [1, 3600, 90 * 86400, 365 * 86400])
def test_expiry_preserves_exact_database_time_and_selected_whole_seconds(seconds: int) -> None:
    expiry = ApplicationKeyLifetimePolicy.expires_at(
        issued_at=ISSUED, lifetime_seconds=seconds, maximum_lifetime_seconds=365 * 86400
    )

    assert expiry == ISSUED + timedelta(seconds=seconds)


@pytest.mark.parametrize("seconds", [True, False, 0, -1, 2**53])
def test_non_positive_or_inexact_lifetimes_cannot_become_expiries(seconds: int) -> None:
    with pytest.raises(ValueError):
        ApplicationKeyLifetimePolicy.expires_at(
            issued_at=ISSUED,
            lifetime_seconds=seconds,
            maximum_lifetime_seconds=ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS,
        )


def test_selected_lifetime_cannot_exceed_current_fresh_maximum() -> None:
    with pytest.raises(ValueError):
        ApplicationKeyLifetimePolicy.expires_at(
            issued_at=ISSUED, lifetime_seconds=3601, maximum_lifetime_seconds=3600
        )


@pytest.mark.parametrize("maximum", [True, 0, -1, 2**53])
def test_incoherent_maximum_cannot_authorize_an_expiry(maximum: int) -> None:
    with pytest.raises(ValueError):
        ApplicationKeyLifetimePolicy.expires_at(
            issued_at=ISSUED, lifetime_seconds=1, maximum_lifetime_seconds=maximum
        )


@pytest.mark.parametrize(
    "issued,seconds",
    [
        (datetime.max.replace(tzinfo=UTC) - timedelta(seconds=1), 2),
        (ISSUED, ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS),
    ],
)
def test_timestamp_and_timedelta_overflow_are_safe_validation_failures(
    issued: datetime, seconds: int
) -> None:
    with pytest.raises(ValueError, match="expiry"):
        ApplicationKeyLifetimePolicy.expires_at(
            issued_at=issued,
            lifetime_seconds=seconds,
            maximum_lifetime_seconds=ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS,
        )


@pytest.mark.parametrize(
    "issued",
    [ISSUED.replace(tzinfo=None), ISSUED.replace(tzinfo=timezone(timedelta(hours=1)))],
)
def test_expiry_requires_the_database_utc_observation(issued: datetime) -> None:
    with pytest.raises(ValueError):
        ApplicationKeyLifetimePolicy.expires_at(
            issued_at=issued, lifetime_seconds=1, maximum_lifetime_seconds=3600
        )
