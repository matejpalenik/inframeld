"""Issue one disposable account gateway identity without persisting a CA signing key."""

import json
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
        Path("/run/account-recovery-key"),
        Path("/run/account-recovery-kratos"),
    )
    if os.geteuid() != 0:
        raise RuntimeError("Disposable volume initialization requires container root.")
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
        if any(directory.iterdir()):
            raise RuntimeError("Account fixture volumes must be fresh and empty.")
        directory.chmod(0o755 if directory.name == "account-trust" else 0o700)
        if directory.name == "account-recovery-kratos":
            os.chown(directory, 10000, -1)
        else:
            os.chown(directory, 10001, 10001)
    # Match the existing private native-recovery forwarder's fixture-only key.
    key = "inframeld-native-recovery-hook-test-only"
    key_file = directories[5] / "hook.key"
    write(key_file, key.encode(), 0o600)
    os.chown(key_file, 10001, -1)

    def hook(phase: str, *, interrupt: bool) -> dict[str, object]:
        return {
            "hook": "web_hook",
            "config": {
                "url": f"http://recovery-hooks:8082/internal/test/native-recovery/{phase}",
                "method": "POST",
                "body": f"file:///etc/recovery/recovery-{phase}.jsonnet",
                "can_interrupt": interrupt,
                "auth": {
                    "type": "api_key",
                    "config": {
                        "name": "X-Inframeld-Recovery-Key",
                        "value": key,
                        "in": "header",
                    },
                },
                "response": {"ignore": False, "parse": False},
            },
        }

    hooks = {
        "selfservice": {
            "flows": {
                "recovery": {
                    "after": {
                        "hooks": [
                            hook("admit", interrupt=True),
                            {"hook": "revoke_active_sessions"},
                        ]
                    }
                },
                "settings": {
                    "before": {"hooks": [hook("settings", interrupt=True)]},
                    "after": {
                        "password": {
                            "hooks": [
                                {"hook": "revoke_active_sessions"},
                                hook("password-saved", interrupt=False),
                            ]
                        }
                    },
                },
            }
        },
    }
    config_file = directories[6] / "hooks.json"
    write(config_file, json.dumps(hooks).encode(), 0o600)
    # Config.User of the exact pinned Kratos image is UID10000. No GID assumption.
    os.chown(config_file, 10000, -1)
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
        "login.identity.test",
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
