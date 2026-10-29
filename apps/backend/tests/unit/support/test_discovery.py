"""Prove discovery ignores request authority and bounds its public disclosure."""

from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from inframeld_backend.access.application.dtos.public_discovery_dto import PublicDiscoveryDTO
from inframeld_backend.access.http.routes.discovery_routes import create_discovery_router
from inframeld_backend.access.infrastructure.settings.discovery_settings import DiscoverySettings
from inframeld_backend.bootstrap.application_settings import ApplicationSettings, get_settings
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers

ID = UUID("11111111-1111-4111-8111-111111111111")


@pytest.mark.parametrize(
    "resource,path",
    [
        ("https://api.test", ""),
        ("https://api.test/", ""),
        ("https://api.test/api/v1", "/api/v1"),
        ("https://api.test/api/", "/api/"),
        ("https://%61pi.test", ""),
        ("https://bücher.test/api%2Fv1", "/api%2Fv1"),
    ],
)
def test_public_metadata_is_exact_and_credential_independent(resource: str, path: str) -> None:
    app = FastAPI()
    app.include_router(
        create_discovery_router(
            lambda: PublicDiscoveryDTO(resource, "https://auth.test/", InstallationId(ID))
        )
    )
    with TestClient(app) as client:
        response = client.get(
            "/.well-known/oauth-protected-resource" + path,
            headers={"Host": "hostile.test", "X-Forwarded-Host": "private-admin.test"},
        )
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "resource": resource,
            "authorization_servers": ["https://auth.test/"],
            "scopes_supported": ["inframeld:api"],
            "bearer_methods_supported": ["header"],
            "inframeld": {
                "schema_version": 1,
                "installation_id": str(ID),
                "client_id": "inframeld-cli",
            },
        }
        assert client.get("/.well-known/oauth-protected-resource/other").status_code == 404


def test_unconfigured_discovery_is_safely_unavailable() -> None:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(create_discovery_router(lambda: None))
    with TestClient(app) as client:
        response = client.get("/.well-known/oauth-protected-resource")
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["status"] == 503


@pytest.mark.parametrize(
    "value",
    [
        "http://api.test",
        "https://user:secret@api.test",
        "https://api.test?secret=x",
        "https://api.test/#x",
        "https://api.test/../admin",
        "https://api.test/has space",
        "https://api.test/\x7f",
        "https://api.test/%7F",
        "https://api.test/%FF",
        "https://api.test/a%GG",
        "https://api.test/a%",
        "https:/api.test/../admin",
        "https:api.test",
        "https://@api.test",
    ],
)
def test_public_url_rejects_unsafe_identifiers(value: str) -> None:
    with pytest.raises(ValidationError):
        DiscoverySettings(public_api_url=value)


def test_managed_profile_requires_literal_loopback() -> None:
    DiscoverySettings(public_api_url="http://127.0.0.1:8000", transport_profile="managed-local")
    with pytest.raises(ValidationError):
        DiscoverySettings(public_api_url="http://localhost:8000", transport_profile="managed-local")


def test_enabled_discovery_requires_matching_provider_configuration() -> None:
    from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
    from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
    from inframeld_backend.bootstrap.application_settings import get_settings

    original = {name: getattr(get_settings(), name) for name in type(get_settings()).model_fields}
    original.update(discovery={"public_api_url": "https://api.test"}, hydra=None)
    with pytest.raises(ValidationError, match="requires Hydra"):
        type(get_settings()).model_validate(original)
    original.update(
        kratos=KratosSettings.model_validate(
            {
                "public_url": "http://kratos:4433",
                "admin_url": "http://kratos:4434",
                "authority": "kratos:test",
            }
        ),
        hydra=HydraSettings.model_validate(
            {
                "admin_url": "http://hydra:4445",
                "issuer": "https://auth.test/",
                "api_audience": "https://other.test",
            }
        ),
    )
    with pytest.raises(ValidationError, match="must equal"):
        type(get_settings()).model_validate(original)


@pytest.mark.asyncio
async def test_failed_identity_reload_cannot_leave_a_public_snapshot() -> None:
    from unittest.mock import AsyncMock, patch

    from inframeld_backend.access.infrastructure.resources.installation_discovery_resource import (
        InstallationDiscoveryResource,
    )
    from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
    from inframeld_backend.bootstrap.application_settings import get_settings
    from inframeld_backend.shared.infrastructure.errors.installation_identity_error import (
        InstallationIdentityError,
    )
    from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
        PostgresInstallationIdentityReader,
    )
    from inframeld_backend.shared.infrastructure.resources.database import Database

    database = Database(get_settings().database)
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
    try:
        with patch.object(
            PostgresInstallationIdentityReader, "read", AsyncMock(return_value=InstallationId(ID))
        ):
            await resource.startup(database)
            assert resource.read() is not None
        with patch.object(
            PostgresInstallationIdentityReader,
            "read",
            AsyncMock(side_effect=InstallationIdentityError("missing")),
        ):
            with pytest.raises(InstallationIdentityError):
                await resource.startup(database)
            assert resource.read() is None
    finally:
        await database.shutdown()


@pytest.mark.parametrize(
    "public,private",
    [
        ("https://admin.test", "https://admin.test/"),
        ("https://ADMIN.test/", "https://admin.test/"),
        ("https://admin.test:443/", "https://admin.test/"),
        ("https://%61dmin.test", "https://admin.test/"),
        ("https://bücher.test/admin/", "https://xn--bcher-kva.test/admin"),
        ("https://[0:0:0:0:0:0:0:1]/admin", "https://[::1]/admin/"),
        ("https://127.1:4445", "https://127.0.0.1:4445/"),
    ],
)
def test_public_identity_cannot_be_the_configured_admin_endpoint(public: str, private: str) -> None:
    from inframeld_backend.access.infrastructure.verifiers.pydantic_discovery_url_verifier import (
        PydanticDiscoveryURLVerifier,
    )

    with pytest.raises(ValueError, match="administration"):
        PydanticDiscoveryURLVerifier.require_not_admin(public, private)


def _discovery_configuration(
    api: str,
    issuer: str,
    *,
    hydra_admin: str = "http://hydra:4445",
    kratos_admin: str = "http://kratos:4434",
) -> dict[str, object]:
    baseline = get_settings()
    return {
        **{name: getattr(baseline, name) for name in type(baseline).model_fields},
        "discovery": {"public_api_url": api},
        "hydra": {
            "admin_url": hydra_admin,
            "issuer": issuer,
            "api_audience": api,
        },
        "kratos": {
            "public_url": "http://kratos:4433",
            "admin_url": kratos_admin,
            "authority": "kratos:test",
        },
    }


@pytest.mark.parametrize("field", ["api", "issuer"])
@pytest.mark.parametrize(
    "value",
    [
        "https://api%GG.test",
        "https://api%2Fadmin.test",
        "https://api%00.test",
        "https://api%5C.test",
    ],
)
def test_enabled_discovery_rejects_invalid_authorities(field: str, value: str) -> None:
    configuration = _discovery_configuration(
        value if field == "api" else "https://api.test",
        value if field == "issuer" else "https://auth.test/",
    )

    with pytest.raises(ValidationError, match="canonical public HTTPS URL"):
        ApplicationSettings.model_validate(configuration)


@pytest.mark.parametrize("field", ["api", "issuer"])
@pytest.mark.parametrize("provider", ["hydra", "kratos"])
def test_admin_alias_is_rejected_for_each_public_identity(field: str, provider: str) -> None:
    configuration = _discovery_configuration(
        "https://%61dmin.test" if field == "api" else "https://api.test",
        "https://%61dmin.test" if field == "issuer" else "https://auth.test/",
        hydra_admin="https://admin.test/" if provider == "hydra" else "http://hydra:4445",
        kratos_admin="https://admin.test/" if provider == "kratos" else "http://kratos:4434",
    )

    with pytest.raises(ValidationError, match="administration endpoint"):
        ApplicationSettings.model_validate(configuration)


@pytest.mark.parametrize(
    "public,private",
    [
        ("https://admin.test/public", "https://admin.test/admin"),
        ("https://admin.test/", "http://admin.test/"),
        ("https://admin.test:8443/", "https://admin.test/"),
        ("https://admin.test:0/", "https://admin.test/"),
    ],
)
def test_admin_guard_preserves_distinct_endpoints(public: str, private: str) -> None:
    from inframeld_backend.access.infrastructure.verifiers.pydantic_discovery_url_verifier import (
        PydanticDiscoveryURLVerifier,
    )

    PydanticDiscoveryURLVerifier.require_not_admin(public, private)


@pytest.mark.parametrize(
    "value",
    [
        "https://api.test",
        "HTTPS://API.test:443/api/",
        "https://private.test:8443/api",
        "https://10.0.0.1/api",
        "https://[2001:db8::1]/api",
        "https://bücher.test/a%20b",
        "https://xn--bcher-kva.test/api",
        "https://%61pi.test/api%2Fv1",
        "https://api.test/a%25b",
        "https://api.test:0/api",
    ],
)
def test_valid_discovery_identifiers_retain_spelling(value: str) -> None:
    settings = ApplicationSettings.model_validate(_discovery_configuration(value, value))

    assert settings.discovery is not None
    assert settings.hydra is not None
    assert settings.discovery.public_api_url == value
    assert settings.hydra.api_audience.value == value
    assert settings.hydra.issuer.value == value


@pytest.mark.parametrize("character", ["a", "é"])
@pytest.mark.parametrize("size", [8192, 8193])
def test_discovery_url_budget_counts_original_utf8_bytes(character: str, size: int) -> None:
    prefix = "https://api.test/"
    count, remainder = divmod(size - len(prefix), len(character.encode("utf-8")))
    value = prefix + character * count + "a" * remainder
    assert len(value.encode("utf-8")) == size

    if size > 8192:
        with pytest.raises(ValidationError, match="canonical public HTTPS URL"):
            ApplicationSettings.model_validate(_discovery_configuration(value, value))
    else:
        settings = ApplicationSettings.model_validate(_discovery_configuration(value, value))
        assert settings.discovery is not None
        assert settings.hydra is not None
        assert settings.discovery.public_api_url == value
        assert settings.hydra.issuer.value == value


@pytest.mark.parametrize(
    "value",
    [
        "HTTP://127.0.0.1:8000",
        "http://127.1:8000",
        "http://2130706433:8000",
        "http://%31%32%37.0.0.1:8000",
        "http://127.0.0.1.:8000",
    ],
)
def test_managed_discovery_rejects_normalized_loopback_aliases(value: str) -> None:
    with pytest.raises(ValidationError):
        DiscoverySettings(public_api_url=value, transport_profile="managed-local")


@pytest.mark.parametrize("operation", ["public", "admin"])
def test_url_parser_failures_do_not_retain_sensitive_input(operation: str) -> None:
    from inframeld_backend.access.infrastructure.verifiers.pydantic_discovery_url_verifier import (
        PydanticDiscoveryURLVerifier,
    )

    sentinel = "private-discovery-credential"
    value = f"https://api%GG.test/{sentinel}"
    with pytest.raises(ValueError, match="canonical public HTTPS URL") as raised:
        if operation == "public":
            PydanticDiscoveryURLVerifier.require_public(value)
        else:
            PydanticDiscoveryURLVerifier.require_not_admin(value, "https://admin.test/")

    assert sentinel not in str(raised.value)
    assert sentinel not in repr(raised.value)
    assert raised.value.__cause__ is None
    assert raised.value.__context__ is None
