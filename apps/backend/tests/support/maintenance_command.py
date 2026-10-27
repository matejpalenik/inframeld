"""Run the installed maintenance command with only database and logging configuration."""

import asyncio
import json
import os

from pydantic import TypeAdapter

from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings


async def run_maintenance(
    request: dict[str, object], settings: DatabaseSettings
) -> tuple[int, dict[str, object]]:
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("INFRAMELD_")
    }
    environment.update(
        {
            "INFRAMELD_DATABASE__HOST": settings.host,
            "INFRAMELD_DATABASE__PORT": str(settings.port),
            "INFRAMELD_DATABASE__NAME": settings.name,
            "INFRAMELD_DATABASE__USER": settings.user,
            "INFRAMELD_DATABASE__PASSWORD": settings.password.get_secret_value(),
            "INFRAMELD_LOG_FORMAT": "json",
        }
    )
    process = await asyncio.create_subprocess_exec(
        "inframeld-maintenance",
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(15):
            output, _ = await process.communicate(json.dumps(request).encode())
        assert process.returncode is not None
        return process.returncode, TypeAdapter(dict[str, object]).validate_python(
            json.loads(output), strict=True
        )
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
