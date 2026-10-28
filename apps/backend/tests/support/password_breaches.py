"""Supply deterministic password-breach responses inside the private test network."""

import ssl
from pathlib import Path as FilePath
from typing import Annotated

import httpx2
from fastapi import FastAPI, Path
from fastapi.responses import PlainTextResponse

from tests.support.integration_services import PASSWORD_BREACHES_URL

BREACHED_PASSWORD = "Test-only-breached-Passphrase-987!"
# Public HIBP protocol vectors, checked independently by native Kratos tests.
BREACHED_PASSWORD_SHA1 = "F9F2973407885FA3286156776CBD37453BC010C2"
CLEAN_PASSWORD = "Test-only-clean-Passphrase-753!"
CLEAN_PASSWORD_PREFIX = "AB3EC"
HashPrefix = Annotated[str, Path(pattern=r"^[0-9a-fA-F]{5}$")]
CA_FILE = FilePath(__file__).resolve().parents[1] / "fixtures/password-breaches/ca.pem"


def create_client() -> httpx2.AsyncClient:
    """Verify the fixture's hostname and test CA without trusting proxy environment variables."""
    return httpx2.AsyncClient(
        base_url=PASSWORD_BREACHES_URL,
        verify=ssl.create_default_context(cafile=str(CA_FILE)),
        timeout=2,
        trust_env=False,
    )


def create_app() -> FastAPI:
    """Own one fixture's lookup counts without storing submitted passwords."""
    application = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    lookups: dict[str, int] = {}

    @application.get("/range/{prefix}", response_class=PlainTextResponse)
    async def lookup(prefix: HashPrefix) -> str:
        normalized = prefix.upper()
        lookups[normalized] = lookups.get(normalized, 0) + 1
        return (
            f"{BREACHED_PASSWORD_SHA1[5:]}:1\n" if normalized == BREACHED_PASSWORD_SHA1[:5] else ""
        )

    @application.get("/observations/{prefix}")
    async def observation(prefix: HashPrefix) -> dict[str, int]:
        return {"requests": lookups.get(prefix.upper(), 0)}

    @application.get("/health/ready")
    async def ready() -> dict[str, str]:
        return {"status": "ready"}

    return application


app = create_app()
