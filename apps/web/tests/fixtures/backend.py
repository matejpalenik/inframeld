"""Run the unchanged production application against this disposable fixture database."""

import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

import uvicorn
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.bootstrap.application_settings import ApplicationSettings
from inframeld_backend.shared.infrastructure.migrations.migration_runner import run_migrations
from inframeld_backend.shared.infrastructure.resources.database import Database
from ory_hydra_client import ApiClient, Configuration, OAuth2Api
from pydantic import BaseModel, ConfigDict
from tests.support.access_scenarios import MockAccessScenarios


class FixtureSubjectDTO(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    subject: UUID


def settings() -> ApplicationSettings:
    configured = ApplicationSettings.model_validate({})
    if (configured.database.host, configured.database.name) != ("postgres", "account_ui_test"):
        raise RuntimeError("Account qualification requires its private disposable database.")
    return configured


async def seed(configured: ApplicationSettings, subject: UUID) -> None:
    database = Database(configured.database)
    await database.startup()
    try:
        async with database.session() as session, session.begin():
            await MockAccessScenarios.seed_linked_human(
                session,
                VerifiedHumanIdentityDTO(
                    IdentityAuthority("kratos:account-ui-test"), IdentitySubject(str(subject))
                ),
            )
    finally:
        await database.shutdown()


def prepare_navigation(configured: ApplicationSettings) -> None:
    """Read official registration for browser decision navigation without exchange."""
    hydra = configured.hydra
    if hydra is None:
        raise RuntimeError("The fixture requires its official OAuth registration.")
    sdk = ApiClient(Configuration(host=str(hydra.admin_url).rstrip("/"), retries=0, debug=False))
    try:
        registration = OAuth2Api(sdk).get_o_auth2_client("inframeld-cli", _request_timeout=5.0)
        redirects = registration.redirect_uris
        if registration.client_id != "inframeld-cli" or redirects is None or len(redirects) != 1:
            raise RuntimeError("The official registration is not available.")
        body = {
            "clientId": registration.client_id,
            "redirectUri": redirects[0],
            "authorizationEndpoint": f"{hydra.issuer.value.rstrip('/')}/oauth2/auth",
            "issuer": hydra.issuer.value,
            "audience": hydra.api_audience.value,
        }
        descriptor = os.open(
            "/run/account-fixture/oauth-navigation.json",
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "w") as destination:
            json.dump(body, destination)
    finally:
        sdk.rest_client.pool_manager.clear()


def main() -> None:
    configured = settings()
    if sys.argv[1:] == ["migrate"]:
        run_migrations(configured.database)
    elif sys.argv[1:] == ["seed"]:
        human = FixtureSubjectDTO.model_validate_json(
            Path("/run/account-fixture/human.json").read_text()
        )
        asyncio.run(seed(configured, human.subject))
        prepare_navigation(configured)
    elif sys.argv[1:] == ["serve"]:
        uvicorn.run(
            "inframeld_backend.main:app",
            host="0.0.0.0",
            port=8000,
            access_log=False,
            log_level="warning",
        )
    else:
        raise RuntimeError("Unknown account fixture command.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("The private account backend fixture failed.", file=sys.stderr)
        raise SystemExit(1) from None
