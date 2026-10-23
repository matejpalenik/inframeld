from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.application.value_objects.oauth_consent_request_id import (
    OAuthConsentRequestId,
)
from inframeld_backend.access.application.value_objects.oauth_login_session_id import (
    OAuthLoginSessionId,
)


@pytest.mark.parametrize("identifier", [OAuthConsentRequestId, OAuthLoginSessionId])
def test_provider_identifier_requires_a_parsed_uuid(
    identifier: type[OAuthConsentRequestId] | type[OAuthLoginSessionId],
) -> None:
    """Parse Hydra's different UUID wire formats at the provider boundary."""
    for invalid in ("not-a-uuid", "0123456789abcdef0123456789abcdef", None, 7):
        with pytest.raises(TypeError, match="parsed UUID"):
            replace(identifier(UUID(int=0)), value=invalid)


def test_provider_identifiers_retain_distinct_meaning_for_the_same_uuid() -> None:
    value = UUID("01234567-89ab-cdef-0123-456789abcdef")
    consent = OAuthConsentRequestId(value)
    login = OAuthLoginSessionId(value)

    assert consent.value == login.value == value
    assert consent != login
    assert len({consent, login}) == 2
