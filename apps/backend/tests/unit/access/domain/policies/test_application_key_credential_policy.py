from datetime import UTC, datetime, timedelta

import pytest

from inframeld_backend.access.domain.policies.application_key_credential_policy import (
    ApplicationKeyCredentialPolicy,
)

NOW = datetime(2030, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "binding, expiry, revoked, expected",
    [
        (True, NOW + timedelta(seconds=1), None, True),
        (True, NOW, None, False),
        (True, NOW - timedelta(seconds=1), None, False),
        (True, None, None, False),
        (False, NOW + timedelta(seconds=1), None, False),
        (True, NOW + timedelta(seconds=1), NOW, False),
    ],
)
def test_expiry_and_revocation_are_checked_at_this_observation(
    binding: bool, expiry: datetime | None, revoked: datetime | None, expected: bool
) -> None:
    assert (
        ApplicationKeyCredentialPolicy.is_current(
            binding_matches=binding, checked_at=NOW, expires_at=expiry, revoked_at=revoked
        )
        is expected
    )
