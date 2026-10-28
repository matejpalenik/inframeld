"""Report bounded startup failures without reflecting credentials or response bodies."""

import ssl
from datetime import UTC, datetime
from pathlib import Path

import httpx2

_RESTART = (
    "Restart the integration stack: ./scripts/dev-compose.sh test-services-down, "
    "then ./scripts/dev-compose.sh test-services-up, "
    "then ./scripts/dev-compose.sh test-run with your original test arguments."
)


def classify_transport_failure(error: httpx2.TransportError) -> str:
    """Inspect structured causes rather than potentially sensitive exception messages."""
    cause: BaseException | None = error
    seen: set[int] = set()
    while cause is not None and id(cause) not in seen:
        seen.add(id(cause))
        if isinstance(cause, ssl.SSLCertVerificationError):
            return (
                "certificate expired"
                if cause.verify_code == 10
                else "certificate verification failed"
            )
        cause = cause.__cause__ or cause.__context__
    return "request timeout" if isinstance(error, httpx2.TimeoutException) else "connection failure"


def describe_readiness_failure(pending: set[str], failures: dict[str, str]) -> str:
    details = ", ".join(f"{name}: {failures.get(name, 'not ready')}" for name in sorted(pending))
    message = f"Test services not ready after 60 seconds: {details}"
    if any(failures.get(name, "").startswith("certificate") for name in pending):
        message += f". {_RESTART}"
    return message


def check_fixture_certificate_expiry(path: Path, *, now: datetime | None = None) -> None:
    """Reject stale or incomplete TLS output before waiting for network readiness."""
    try:
        expiry = datetime.fromisoformat(path.read_text().strip())
        if expiry.tzinfo is None:
            raise ValueError
    except (OSError, ValueError):
        raise RuntimeError(
            f"Fixture certificate expiry metadata is missing or invalid. {_RESTART}"
        ) from None
    if expiry <= (now if now is not None else datetime.now(UTC)):
        raise RuntimeError(
            f"password-breaches: certificate expired at {expiry.isoformat()}. {_RESTART}"
        )
