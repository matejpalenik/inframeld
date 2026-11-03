"""Issue one disposable account gateway identity without persisting a CA signing key."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_bytes

import trustme


def write(path: Path, content: bytes, mode: int) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(descriptor, "wb") as destination:
        destination.write(content)
        os.fchmod(destination.fileno(), mode)


def main() -> None:
    os.umask(0o077)
    directories = (
        Path("/run/account-trust"),
        Path("/run/account-identity"),
        Path("/run/account-secrets"),
        Path("/run/account-fixture"),
        Path("/run/account-proof"),
    )
    if os.geteuid() != 0:
        raise RuntimeError("Disposable volume initialization requires container root.")
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise RuntimeError("Account fixture volumes must be fresh and empty.")
        directory.chmod(0o755 if directory.name == "account-trust" else 0o700)
        os.chown(directory, 10001, 10001)
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
    Path("/run/account-proof/bridge").mkdir(mode=0o700)
    Path("/run/account-proof/denied-bridge").mkdir(mode=0o700)

    now = datetime.now(UTC)
    ca = trustme.CA()
    leaf = ca.issue_cert(
        "inframeld.account.test",
        "hydra.account.test",
        not_before=now - timedelta(minutes=5),
        not_after=now + timedelta(hours=24),
    )
    write(directories[0] / "ca.pem", ca.cert_pem.bytes(), 0o644)
    write(
        directories[0] / "expires.txt",
        (now + timedelta(hours=24)).isoformat().encode(),
        0o644,
    )
    write(directories[1] / "server.key", leaf.private_key_pem.bytes(), 0o600)
    write(
        directories[1] / "server.pem",
        b"".join(cert.bytes() for cert in leaf.cert_chain_pems),
        0o644,
    )
    write(directories[2] / "fingerprint.key", token_bytes(32), 0o600)


if __name__ == "__main__":
    main()
