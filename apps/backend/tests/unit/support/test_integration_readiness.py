"""Keep TLS recovery actionable without disclosing upstream error content."""

import ssl
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest
from tests.support.integration_readiness import (
    check_fixture_certificate_expiry,
    classify_transport_failure,
    describe_readiness_failure,
)


@pytest.mark.parametrize(
    "code, expected",
    [
        (10, "certificate expired"),
        (62, "certificate verification failed"),
        (20, "certificate verification failed"),
    ],
)
def test_structured_certificate_errors_are_classified_without_sensitive_text(
    code: int, expected: str
) -> None:
    certificate = ssl.SSLCertVerificationError("secret upstream text")
    certificate.verify_code = code
    wrapped = httpx2.ConnectError("https://user:secret@service/private")
    wrapped.__cause__ = certificate
    assert classify_transport_failure(wrapped) == expected
    message = describe_readiness_failure({"password-breaches"}, {"password-breaches": expected})
    assert "secret" not in message
    assert "test-services-down" in message
    assert "test-services-up" in message
    assert "test-run" in message


@pytest.mark.parametrize(
    "error, expected",
    [
        (httpx2.ConnectError("secret"), "connection failure"),
        (httpx2.ReadTimeout("secret"), "request timeout"),
    ],
)
def test_transport_failure_categories_are_safe(error: httpx2.TransportError, expected: str) -> None:
    assert classify_transport_failure(error) == expected


def test_readiness_message_names_status_and_only_pending_services() -> None:
    message = describe_readiness_failure(
        {"fixture"}, {"fixture": "HTTP 503", "ready": "connection failure"}
    )
    assert "fixture: HTTP 503" in message
    assert "ready:" not in message


def test_expired_fixture_is_rejected_before_readiness(tmp_path: Path) -> None:
    expiry = tmp_path / "server-not-after.txt"
    now = datetime.now(UTC)
    expiry.write_text((now - timedelta(seconds=1)).isoformat())
    with pytest.raises(RuntimeError, match="certificate expired") as caught:
        check_fixture_certificate_expiry(expiry, now=now)
    assert "test-services-up" in str(caught.value)


def test_current_fixture_can_proceed_to_readiness(tmp_path: Path) -> None:
    expiry = tmp_path / "server-not-after.txt"
    expiry.write_text((datetime.now(UTC) + timedelta(hours=1)).isoformat())
    check_fixture_certificate_expiry(expiry)


@pytest.mark.parametrize("contents", [None, "secret invalid expiry", "2026-01-01T00:00:00"])
def test_invalid_expiry_fails_without_reflecting_contents(
    tmp_path: Path, contents: str | None
) -> None:
    expiry = tmp_path / "server-not-after.txt"
    if contents is not None:
        expiry.write_text(contents)
    with pytest.raises(RuntimeError) as caught:
        check_fixture_certificate_expiry(expiry)
    assert "secret" not in str(caught.value)
    assert "test-services-up" in str(caught.value)
