"""Wait, migrate and run the complete suite inside the private test network."""

import asyncio
import os
import secrets
import subprocess
import sys
from pathlib import Path

import httpx2
from sqlalchemy import literal, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from inframeld_backend.bootstrap.application_settings import get_settings
from tests.support.integration_services import (
    EXPIRING_KRATOS_PUBLIC_URL,
    HYDRA_ADMIN_URL,
    KRATOS_PUBLIC_URL,
    LIFETIME_HYDRA_ADMIN_URL,
    MAILPIT_URL,
    MOCK_OIDC_URL,
    POSTGRES_HOST,
    POSTGRES_PORT,
    RECOVERY_HOOKS_URL,
)
from tests.support.postgres import database_url


async def _wait_for_database(engine: AsyncEngine, pending: set[str]) -> None:
    while True:
        try:
            async with engine.connect() as connection:
                await connection.execute(select(literal(1)))
        except OperationalError:
            await asyncio.sleep(0.25)
        else:
            pending.remove("postgres")
            return


async def _wait_for_http(
    client: httpx2.AsyncClient, name: str, url: str, pending: set[str]
) -> None:
    while True:
        try:
            response = await client.get(url)
        except httpx2.TransportError:
            pass
        else:
            if response.status_code == 200:
                pending.remove(name)
                return
        await asyncio.sleep(0.25)


async def _wait_for_services() -> None:
    """Share one startup deadline, with service names rather than sensitive error bodies."""
    settings = get_settings().database
    if (settings.host, settings.port) != (POSTGRES_HOST, POSTGRES_PORT):
        raise RuntimeError("The integration runner requires the private test database endpoint.")
    endpoints = {
        "kratos": f"{KRATOS_PUBLIC_URL}/health/ready",
        "kratos-expiring": f"{EXPIRING_KRATOS_PUBLIC_URL}/health/ready",
        "hydra": f"{HYDRA_ADMIN_URL}/health/ready",
        "hydra-lifetimes": f"{LIFETIME_HYDRA_ADMIN_URL}/health/ready",
        "mailpit": f"{MAILPIT_URL}/readyz",
        "mock-oidc": f"{MOCK_OIDC_URL}/isalive",
        "recovery-hooks": f"{RECOVERY_HOOKS_URL}/health/ready",
    }
    pending = {"postgres", *endpoints}
    engine = create_async_engine(
        database_url(settings),
        connect_args={"connect_timeout": 2},
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        async with (
            httpx2.AsyncClient(timeout=2.0, trust_env=False) as client,
            asyncio.timeout(60.0),
            asyncio.TaskGroup() as tasks,
        ):
            tasks.create_task(_wait_for_database(engine, pending))
            for name, url in endpoints.items():
                tasks.create_task(_wait_for_http(client, name, url, pending))
    except TimeoutError:
        raise RuntimeError(
            f"Test services not ready after 60 seconds: {', '.join(sorted(pending))}"
        ) from None
    finally:
        await engine.dispose()
    print("Integration services are ready on the private Compose network.", flush=True)


def main() -> int:
    key = Path("/tmp/fingerprint.key")
    key.write_bytes(secrets.token_bytes(32))
    key.chmod(0o600)
    asyncio.run(_wait_for_services())
    migrated = subprocess.run([sys.executable, "-m", "inframeld_backend.migrate"], check=False)
    if migrated.returncode != 0:
        return migrated.returncode
    targets = sys.argv[1:] or ["tests/integration"]
    os.execv(
        sys.executable,
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "--tb=short", "-q", *targets],
    )


if __name__ == "__main__":
    raise SystemExit(main())
