"""Read the existing installation identity without initializing or replacing it."""

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from inframeld_backend.access.http.routes.discovery_routes import create_discovery_router
from inframeld_backend.access.infrastructure.resources.installation_discovery_resource import (
    InstallationDiscoveryResource,
)
from inframeld_backend.access.infrastructure.settings.discovery_settings import DiscoverySettings
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires private integration PostgreSQL",
)


@pytest.mark.asyncio
async def test_public_identity_survives_discovery_resource_restart(database: Database) -> None:
    original = await PostgresInstallationIdentityReader(database).read()
    settings = DiscoverySettings(public_api_url="https://api.test")
    hydra = HydraSettings.model_validate(
        {
            "admin_url": "http://hydra:4445",
            "issuer": "https://auth.test/",
            "api_audience": "https://api.test",
        }
    )
    for _ in range(2):
        resource = InstallationDiscoveryResource(settings, hydra)
        await resource.startup(database)
        app = FastAPI()
        app.include_router(create_discovery_router(resource.read))
        with TestClient(app) as client:
            response = client.get("/.well-known/oauth-protected-resource")
            assert response.status_code == 200
            assert response.json()["inframeld"]["installation_id"] == str(original.value)
    assert await PostgresInstallationIdentityReader(database).read() == original


@pytest.mark.asyncio
async def test_missing_identity_prevents_publication(database: Database) -> None:
    from sqlalchemy import delete

    from inframeld_backend.shared.infrastructure.errors.installation_identity_error import (
        InstallationIdentityError,
    )
    from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
        InstallationIdentityRow,
    )

    async with database.session() as session:
        await session.execute(delete(InstallationIdentityRow))
        await session.commit()
    resource = InstallationDiscoveryResource(
        DiscoverySettings(public_api_url="https://api.test"),
        HydraSettings.model_validate(
            {
                "admin_url": "http://hydra:4445",
                "issuer": "https://auth.test/",
                "api_audience": "https://api.test",
            }
        ),
    )
    with pytest.raises(InstallationIdentityError):
        await resource.startup(database)
    assert resource.read() is None


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_HYDRA_INTEGRATION") != "1", reason="Requires private Hydra"
)
async def test_published_profile_matches_real_provider_observations(database: Database) -> None:
    """Compare the public projection to real Ory facts inside the HTTP-only private graph.

    Public HTTPS policy is tested separately. Private service addresses are test
    observations, not a supported externally registered transport profile.
    """
    import httpx2
    from pydantic import BaseModel
    from tests.support.hydra_provider import API_AUDIENCE, CLIENT_ID, hydra_test_provider
    from tests.support.integration_services import HYDRA_ADMIN_URL, HYDRA_PUBLIC_URL

    from inframeld_backend.access.application.dtos.public_discovery_dto import PublicDiscoveryDTO

    class ProviderObservation(BaseModel):
        issuer: str
        code_challenge_methods_supported: list[str]

    class ClientObservation(BaseModel):
        client_id: str
        audience: list[str]
        token_endpoint_auth_method: str

    identity = await PostgresInstallationIdentityReader(database).read()
    async with hydra_test_provider(), httpx2.AsyncClient(timeout=5, trust_env=False) as client:
        issuer_response = await client.get(f"{HYDRA_PUBLIC_URL}/.well-known/openid-configuration")
        assert issuer_response.status_code == 200
        provider = ProviderObservation.model_validate_json(issuer_response.content)
        client_response = await client.get(f"{HYDRA_ADMIN_URL}/admin/clients/{CLIENT_ID}")
        assert client_response.status_code == 200
        registered = ClientObservation.model_validate_json(client_response.content)
        snapshot = PublicDiscoveryDTO(API_AUDIENCE.value, HYDRA_PUBLIC_URL + "/", identity)
        app = FastAPI()
        app.include_router(create_discovery_router(lambda: snapshot))
        with TestClient(app) as browser:
            response = browser.get("/.well-known/oauth-protected-resource")
        assert response.status_code == 200
        metadata = response.json()
        assert metadata["authorization_servers"] == [provider.issuer]
        assert "S256" in provider.code_challenge_methods_supported
        assert metadata["resource"] in registered.audience
        assert metadata["inframeld"]["client_id"] == registered.client_id
        assert registered.token_endpoint_auth_method == "none"
