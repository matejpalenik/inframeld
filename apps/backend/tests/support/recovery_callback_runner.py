"""Run the private app against a disposable integration database, never a host database."""

import sys
from pathlib import Path

import uvicorn

from inframeld_backend.bootstrap.recovery_application_settings import RecoveryApplicationSettings
from inframeld_backend.shared.infrastructure.migrations.migration_runner import run_migrations


def main() -> None:
    settings = RecoveryApplicationSettings.model_validate({})
    if (settings.database.host, settings.database.name) != (
        "recovery-postgres",
        "recovery_delivery_test",
    ):
        raise RuntimeError("The callback qualification requires its disposable database.")
    if sys.argv[1:] == ["migrate"]:
        run_migrations(settings.database)
        return
    key = Path("/tmp/recovery-hook.key")
    key.write_bytes(b"inframeld-native-recovery-hook-test-only")
    key.chmod(0o600)
    uvicorn.run(
        "inframeld_backend.recovery_main:app",
        host="0.0.0.0",
        port=8081,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
