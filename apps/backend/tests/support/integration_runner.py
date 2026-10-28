"""Wait, migrate and run the complete suite inside the private test network."""

import asyncio
import os
import secrets
import subprocess
import sys
from pathlib import Path

import httpx2
from pydantic import BaseModel
from sqlalchemy import literal, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from inframeld_backend.bootstrap.application_settings import get_settings
from tests.support.integration_readiness import (
    check_fixture_certificate_expiry,
    classify_transport_failure,
    describe_readiness_failure,
)
from tests.support.integration_services import (
    EXPIRING_KRATOS_PUBLIC_URL,
    HYDRA_ADMIN_URL,
    HYDRA_PUBLIC_URL,
    KRATOS_PUBLIC_URL,
    LIFETIME_HYDRA_ADMIN_URL,
    LIFETIME_HYDRA_PUBLIC_URL,
    MAILPIT_URL,
    MOCK_OIDC_URL,
    PASSWORD_BREACHES_URL,
    POSTGRES_HOST,
    POSTGRES_PORT,
    RECOVERY_HOOKS_URL,
    TLS_EXPIRY_FILE,
)
from tests.support.password_breaches import create_client as create_password_breaches_client
from tests.support.postgres import database_url


async def _wait_for_database(
    engine: AsyncEngine, pending: set[str], failures: dict[str, str]
) -> None:
    while True:
        try:
            async with engine.connect() as connection:
                await connection.execute(select(literal(1)))
        except OperationalError:
            failures["postgres"] = "connection failure"
            await asyncio.sleep(0.25)
        else:
            pending.remove("postgres")
            failures.pop("postgres", None)
            return


async def wait_for_http(
    client: httpx2.AsyncClient,
    name: str,
    url: str,
    pending: set[str],
    failures: dict[str, str] | None = None,
) -> None:
    while True:
        try:
            response = await client.get(url)
        except httpx2.TransportError as error:
            if failures is not None:
                failures[name] = classify_transport_failure(error)
        else:
            if response.status_code == 200:
                pending.remove(name)
                if failures is not None:
                    failures.pop(name, None)
                return
            if failures is not None:
                failures[name] = f"HTTP {response.status_code}"
        await asyncio.sleep(0.25)


class _PublicKeySet(BaseModel):
    keys: list[dict[str, object]]


async def wait_for_hydra_signing_keys(
    client: httpx2.AsyncClient,
    name: str,
    public_url: str,
    pending: set[str],
    failures: dict[str, str] | None = None,
) -> None:
    """Let native key creation finish within the runner's shared startup deadline."""
    while True:
        try:
            response = await client.get(f"{public_url}/.well-known/jwks.json", timeout=30.0)
            if response.status_code != 200:
                if failures is not None:
                    failures[name] = f"HTTP {response.status_code}"
            elif _PublicKeySet.model_validate_json(response.content).keys:
                pending.remove(name)
                if failures is not None:
                    failures.pop(name, None)
                return
            elif failures is not None:
                failures[name] = "signing keys unavailable"
        except httpx2.TransportError as error:
            if failures is not None:
                failures[name] = classify_transport_failure(error)
        except ValueError:
            if failures is not None:
                failures[name] = "invalid signing keys"
        await asyncio.sleep(0.25)


async def _wait_for_services() -> None:
    """Share one startup deadline, with service names rather than sensitive error bodies."""
    check_fixture_certificate_expiry(TLS_EXPIRY_FILE)
    failures: dict[str, str] = {}
    settings = get_settings().database
    if (settings.host, settings.port) != (POSTGRES_HOST, POSTGRES_PORT):
        raise RuntimeError("The integration runner requires the private test database endpoint.")
    endpoints = {
        "kratos": f"{KRATOS_PUBLIC_URL}/health/ready",
        "recovery-callbacks": "http://recovery-callbacks:8081/health",
        "recovery-execution-callbacks": "http://recovery-execution-callbacks:8081/health",
        "kratos-recovery-execution": "http://kratos-recovery-execution:4433/health/ready",
        "kratos-recovery": "http://kratos-recovery:4433/health/ready",
        "kratos-expiring": f"{EXPIRING_KRATOS_PUBLIC_URL}/health/ready",
        "hydra": f"{HYDRA_ADMIN_URL}/health/ready",
        "hydra-lifetimes": f"{LIFETIME_HYDRA_ADMIN_URL}/health/ready",
        "mailpit": f"{MAILPIT_URL}/readyz",
        "mock-oidc": f"{MOCK_OIDC_URL}/isalive",
        "recovery-hooks": f"{RECOVERY_HOOKS_URL}/health/ready",
    }
    key_endpoints = {
        "hydra-signing-keys": HYDRA_PUBLIC_URL,
        "hydra-lifetimes-signing-keys": LIFETIME_HYDRA_PUBLIC_URL,
    }
    pending = {"postgres", "password-breaches", *endpoints, *key_endpoints}
    engine = create_async_engine(
        database_url(settings),
        connect_args={"connect_timeout": 2},
        poolclass=NullPool,
        hide_parameters=True,
    )
    try:
        async with (
            httpx2.AsyncClient(timeout=2.0, trust_env=False) as client,
            create_password_breaches_client() as breach_client,
            asyncio.timeout(60.0),
            asyncio.TaskGroup() as tasks,
        ):
            tasks.create_task(_wait_for_database(engine, pending, failures))
            tasks.create_task(
                wait_for_http(
                    breach_client,
                    "password-breaches",
                    f"{PASSWORD_BREACHES_URL}/health/ready",
                    pending,
                    failures,
                )
            )
            for name, url in endpoints.items():
                tasks.create_task(wait_for_http(client, name, url, pending, failures))
            for name, public_url in key_endpoints.items():
                tasks.create_task(
                    wait_for_hydra_signing_keys(client, name, public_url, pending, failures)
                )
    except TimeoutError:
        raise RuntimeError(describe_readiness_failure(pending, failures)) from None
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
