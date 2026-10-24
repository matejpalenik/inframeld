import pytest

from inframeld_backend.access.application.value_objects.oauth_client_id import OAuthClientId
from inframeld_backend.access.application.value_objects.oauth_consent_challenge import (
    OAuthConsentChallenge,
)


@pytest.mark.parametrize("value", ["", " ", "bad\nchallenge", "bad\tchallenge", "a b"])
def test_invalid_challenge_is_rejected_without_printing_its_contents(value: str) -> None:
    with pytest.raises(ValueError) as caught:
        OAuthConsentChallenge(value)
    assert "bad" not in str(caught.value)


def test_opaque_challenge_is_preserved_and_hidden() -> None:
    value = "private/challenge+payload="
    challenge = OAuthConsentChallenge(value)
    assert challenge.value == value
    assert value not in repr(challenge)


@pytest.mark.parametrize("value", ["", " "])
def test_client_requires_a_nonblank_identifier(value: str) -> None:
    with pytest.raises(ValueError):
        OAuthClientId(value)
