"""Exercise the production command with disposable state and bounded process cleanup."""

import asyncio
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from pydantic import SecretStr

from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

EXECUTION_DATABASE = DatabaseSettings(
    host="recovery-execution-postgres",
    name="recovery_execution_test",
    user="recovery_execution",
    password=SecretStr("recovery-execution-test-only"),
)
EXECUTION_PUBLIC = "http://kratos-recovery-execution:4433"


@asynccontextmanager
async def recovery_worker_process(
    *, admin_url: str = "http://hydra:4445"
) -> AsyncGenerator[asyncio.subprocess.Process]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("INFRAMELD_")
    }
    environment.update(
        {
            "INFRAMELD_DATABASE__HOST": EXECUTION_DATABASE.host,
            "INFRAMELD_DATABASE__NAME": EXECUTION_DATABASE.name,
            "INFRAMELD_DATABASE__USER": EXECUTION_DATABASE.user,
            "INFRAMELD_DATABASE__PASSWORD": EXECUTION_DATABASE.password.get_secret_value(),
            "INFRAMELD_DATABASE__POOL_SIZE": "2",
            "INFRAMELD_DATABASE__MAX_OVERFLOW": "0",
            "INFRAMELD_RECOVERY_CLEANUP__AUTHORITY": EXECUTION_PUBLIC,
            "INFRAMELD_RECOVERY_CLEANUP__HYDRA_ADMIN_URL": admin_url,
            "INFRAMELD_LOG_FORMAT": "json",
        }
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "inframeld_backend.recovery_worker",
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    ready = asyncio.Event()

    async def drain() -> None:
        assert process.stdout is not None
        async for line in process.stdout:
            if b"recovery_worker_ready" in line:
                ready.set()

    reader = asyncio.create_task(drain())
    try:
        async with asyncio.timeout(10):
            await ready.wait()
        assert process.returncode is None, (
            "The production recovery command exited before readiness."
        )
        yield process
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                async with asyncio.timeout(16):
                    await process.wait()
            except TimeoutError:
                process.kill()
                await process.wait()
                raise AssertionError("Recovery worker exceeded its shutdown grace.") from None
        await reader
        assert process.returncode == 0, "The production recovery command failed."
