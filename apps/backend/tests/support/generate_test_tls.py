"""Issue disposable TLS identities before the private integration stack starts."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import trustme

from tests.support.integration_services import TLS_IDENTITY_DIRECTORY, TLS_TRUST_DIRECTORY


def generate_certificates(
    trust_directory: Path, identity_directory: Path, *, now: datetime | None = None
) -> None:
    """Write one stack's public trust and private server identity into empty directories."""
    for directory, mode in ((trust_directory, 0o755), (identity_directory, 0o700)):
        directory.mkdir(parents=True, exist_ok=True, mode=mode)
        directory.chmod(mode)
        if any(directory.iterdir()):
            raise ValueError(f"Certificate output directory must be empty: {directory}")

    issued_at = now if now is not None else datetime.now(UTC)
    ca = trustme.CA()
    server = ca.issue_cert(
        "password-breaches",
        not_before=issued_at - timedelta(minutes=5),
        not_after=issued_at + timedelta(hours=24),
    )
    _write_file(identity_directory / "server.key", server.private_key_pem.bytes(), mode=0o600)
    _write_file(
        identity_directory / "server.pem",
        b"".join(certificate.bytes() for certificate in server.cert_chain_pems),
        mode=0o644,
    )
    _write_file(trust_directory / "ca.pem", ca.cert_pem.bytes(), mode=0o644)
    _write_file(
        trust_directory / "server-not-after.txt",
        (issued_at + timedelta(hours=24)).replace(microsecond=0).isoformat().encode(),
        mode=0o644,
    )


def _write_file(path: Path, content: bytes, *, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as destination:
        destination.write(content)
        os.fchmod(destination.fileno(), mode)


def main() -> None:
    """Prepare fresh volume ownership, then generate as the unprivileged fixture user."""
    if os.geteuid() != 0:
        raise RuntimeError(
            "TLS volume initialization requires container root before dropping privileges"
        )

    os.umask(0o077)
    for directory in (TLS_TRUST_DIRECTORY, TLS_IDENTITY_DIRECTORY):
        directory.mkdir(parents=True, exist_ok=True)
        os.chown(directory, 10001, 10001)
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)

    generate_certificates(TLS_TRUST_DIRECTORY, TLS_IDENTITY_DIRECTORY)
    print("Disposable TLS material generated for password-breaches.")


if __name__ == "__main__":
    main()
