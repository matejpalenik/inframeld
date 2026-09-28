import pytest

from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)

PURPOSE = "provider-credential-update:v1"
CANONICAL_REQUEST = b'{"revision":1,"secret":"alpha"}'


def test_produces_the_reviewed_hmac_sha256_fingerprint() -> None:
    """Pin the stored fingerprint format, including domain and purpose framing."""
    service = RequestFingerprintService(RequestFingerprintKey(b"K" * 32))

    fingerprint = service.fingerprint(
        purpose=PURPOSE,
        canonical_request=CANONICAL_REQUEST,
    )

    assert fingerprint.hex() == ("1cb17af4d9a31b49205c08abdd1772242d8986bcea859af4d6aedd2f3c36aa60")


def test_same_request_has_the_same_fingerprint() -> None:
    """Let an unchanged retry match the fingerprint saved for its first request."""
    service = RequestFingerprintService(RequestFingerprintKey(b"K" * 32))

    first = service.fingerprint(purpose=PURPOSE, canonical_request=CANONICAL_REQUEST)
    retry = service.fingerprint(purpose=PURPOSE, canonical_request=CANONICAL_REQUEST)

    assert retry == first


def test_changed_meaning_purpose_or_key_changes_the_fingerprint() -> None:
    """Separate changed credentials and operations; show why the key must stay stable."""
    service = RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    original = service.fingerprint(purpose=PURPOSE, canonical_request=CANONICAL_REQUEST)

    assert (
        service.fingerprint(
            purpose=PURPOSE,
            canonical_request=b'{"revision":1,"secret":"beta"}',
        )
        != original
    )
    assert (
        service.fingerprint(
            purpose="provider-credential-create:v1",
            canonical_request=CANONICAL_REQUEST,
        )
        != original
    )
    assert (
        RequestFingerprintService(RequestFingerprintKey(b"Z" * 32)).fingerprint(
            purpose=PURPOSE,
            canonical_request=CANONICAL_REQUEST,
        )
        != original
    )


@pytest.mark.parametrize("purpose", ["", "   ", " leading-space"])
def test_rejects_an_invalid_purpose(purpose: str) -> None:
    """Reject blank or padded labels that could silently change retry identity."""
    service = RequestFingerprintService(RequestFingerprintKey(b"K" * 32))

    with pytest.raises(ValueError, match="Fingerprint purpose"):
        service.fingerprint(purpose=purpose, canonical_request=CANONICAL_REQUEST)
