"""Run the production loop with private database state and bounded subprocess cleanup."""

import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from tests.support.seaweedfs_fixture import storage_settings


def _environment(database: DatabaseSettings) -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("INFRAMELD_")
    }
    environment.update(
        {
            "INFRAMELD_DATABASE__HOST": database.host,
            "INFRAMELD_DATABASE__PORT": str(database.port),
            "INFRAMELD_DATABASE__NAME": database.name,
            "INFRAMELD_DATABASE__USER": database.user,
            "INFRAMELD_DATABASE__PASSWORD": database.password.get_secret_value(),
            "INFRAMELD_DATABASE__POOL_SIZE": "2",
            "INFRAMELD_DATABASE__MAX_OVERFLOW": "0",
            "INFRAMELD_JOBS__LEASE_SECONDS": "3",
            "INFRAMELD_JOBS__DATABASE_TIMEOUT_SECONDS": "1",
            "INFRAMELD_JOBS__POLL_SECONDS": "0.1",
            "INFRAMELD_JOBS__SHUTDOWN_SECONDS": "2",
            "INFRAMELD_JOBS__WORK_SECONDS": "60",
            "INFRAMELD_LOG_FORMAT": "json",
        }
    )
    artifacts = storage_settings()
    environment.update(
        {
            "INFRAMELD_ARTIFACT_STORAGE__ENDPOINT_URL": artifacts.endpoint_url,
            "INFRAMELD_ARTIFACT_STORAGE__BUCKET": artifacts.bucket,
            "INFRAMELD_ARTIFACT_STORAGE__ACCESS_KEY_ID": artifacts.access_key_id.get_secret_value(),
            "INFRAMELD_ARTIFACT_STORAGE__SECRET_ACCESS_KEY": artifacts.secret_access_key.get_secret_value(),
            "INFRAMELD_ARTIFACT_STORAGE__REGION": artifacts.region,
            "INFRAMELD_ARTIFACT_STORAGE__MAX_OBJECT_BYTES": str(artifacts.max_object_bytes),
        }
    )
    if artifacts.ca_bundle is not None:
        environment["INFRAMELD_ARTIFACT_STORAGE__CA_BUNDLE"] = str(artifacts.ca_bundle)
    return environment


@asynccontextmanager
async def application_worker_process(
    database: DatabaseSettings,
    *,
    allow_killed: bool = False,
    artifact_cleanup: bool = False,
    delete_journal: Path | None = None,
    crash_after_delete: ArtifactAttemptId | None = None,
) -> AsyncGenerator[tuple[asyncio.subprocess.Process, list[int]]]:
    environment = _environment(database)
    module = (
        "inframeld_backend.application_worker"
        if artifact_cleanup
        else "tests.support.application_job_worker"
    )
    arguments: list[str] = []
    if delete_journal is not None:
        assert artifact_cleanup
        module = "tests.support.observed_artifact_cleanup_worker"
        arguments.append(str(delete_journal))
        if crash_after_delete is not None:
            assert allow_killed
            arguments.append(crash_after_delete.value.hex)
    else:
        assert crash_after_delete is None
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        module,
        *arguments,
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    ready = asyncio.Event()
    units: list[int] = []
    diagnostic: list[str] = []

    async def drain() -> None:
        assert process.stdout is not None
        async for line in process.stdout:
            if b"NotImplementedError" in line and not diagnostic:
                diagnostic.append("runtime_not_implemented")
            if b"application_worker_ready" in line:
                ready.set()
            if line.startswith(b"fixture_unit_completed:"):
                units.append(int(line.split(b":", 1)[1]))

    reader = asyncio.create_task(drain())
    waiter = asyncio.create_task(process.wait())
    readiness = asyncio.create_task(ready.wait())

    async def cleanup() -> None:
        forced = False
        if process.returncode is None:
            process.terminate()
            try:
                async with asyncio.timeout(4):
                    await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()
                forced = True
        await reader
        await waiter
        readiness.cancel()
        await asyncio.gather(readiness, return_exceptions=True)
        assert not forced, "The application worker exceeded its shutdown grace."
        assert process.returncode == 0 or (allow_killed and process.returncode == -9), (
            "The application worker failed: " + ",".join(diagnostic)
        )

    try:
        async with asyncio.timeout(10):
            await asyncio.wait((waiter, readiness), return_when=asyncio.FIRST_COMPLETED)
        assert ready.is_set(), "The application worker exited before readiness: " + ",".join(
            diagnostic
        )
        yield process, units
    finally:
        task = asyncio.create_task(cleanup())
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await asyncio.gather(task, return_exceptions=True)
            raise


async def application_worker_command(database: DatabaseSettings) -> tuple[int, str]:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "inframeld_backend.application_worker",
        env=_environment(database),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        async with asyncio.timeout(10):
            output, _ = await process.communicate()
        assert process.returncode is not None
        return process.returncode, output.decode("utf-8", errors="replace")
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
