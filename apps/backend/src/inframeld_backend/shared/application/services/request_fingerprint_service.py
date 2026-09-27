"""Calculate stable, domain-separated fingerprints of meaningful request input."""

from hmac import digest

from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)

_DOMAIN = b"inframeld:idempotency:v1\x00"


class RequestFingerprintService:
    """Fingerprint canonical bytes supplied by the operation that owns their meaning."""

    def __init__(self, key: RequestFingerprintKey) -> None:
        self._key = key

    def fingerprint(self, *, purpose: str, canonical_request: bytes) -> bytes:
        """Return a domain-separated HMAC of the caller's canonical request bytes.

        The owning operation decides which validated fields those bytes include.
        Its purpose label and the injected key must remain stable while matching
        idempotency reservations are retained.
        """

        if not purpose or purpose != purpose.strip():
            raise ValueError("Fingerprint purpose must be nonblank without surrounding spaces.")

        purpose_bytes = purpose.encode("utf-8")

        if len(purpose_bytes) > 128:
            raise ValueError("Fingerprint purpose must be at most 128 bytes.")

        message = (
            _DOMAIN + len(purpose_bytes).to_bytes(2, "big") + purpose_bytes + canonical_request
        )

        return digest(self._key.value, message, "sha256")
