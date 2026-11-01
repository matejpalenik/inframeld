"""Send actual recipient proof only through protected subprocess stdin."""

import asyncio
import json
import os

from pydantic import TypeAdapter

from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from tests.support.hydra_provider import API_AUDIENCE, HYDRA_ISSUER
from tests.support.integration_services import HYDRA_ADMIN_URL, KRATOS_ADMIN_URL, KRATOS_PUBLIC_URL


async def run_project_metadata_maintenance(
    request: dict[str, object], settings: DatabaseSettings
) -> tuple[int, dict[str, object], bytes]:
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
            "INFRAMELD_KRATOS__PUBLIC_URL": KRATOS_PUBLIC_URL,
            "INFRAMELD_KRATOS__ADMIN_URL": KRATOS_ADMIN_URL,
            "INFRAMELD_KRATOS__AUTHORITY": "kratos:test",
            "INFRAMELD_HYDRA__ADMIN_URL": HYDRA_ADMIN_URL,
            "INFRAMELD_HYDRA__ISSUER": HYDRA_ISSUER.value,
            "INFRAMELD_HYDRA__API_AUDIENCE": API_AUDIENCE.value,
            "INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE": str(
                get_settings().request_fingerprint.key_file
            ),
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
        async with asyncio.timeout(30):
            output, diagnostics = await process.communicate(json.dumps(request).encode("utf-8"))
        try:
            result = TypeAdapter(dict[str, object]).validate_python(json.loads(output), strict=True)
        except (ValueError, TypeError):
            raise AssertionError("Maintenance returned an invalid safe result.") from None
        assert process.returncode is not None
        return process.returncode, result, diagnostics
    finally:
        if process.returncode is None:
            process.kill()
            await process.communicate()
