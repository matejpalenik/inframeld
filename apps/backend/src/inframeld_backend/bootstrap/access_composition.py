"""Assemble Access adapters and application services for one API instance."""

from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api_client import ApiClient
from ory_kratos_client.configuration import Configuration

from inframeld_backend.access.application.services.human_session_authentication_service import (
    HumanSessionAuthenticationService,
)
from inframeld_backend.access.application.services.unavailable_human_session_authentication_service import (
    UnavailableHumanSessionAuthenticationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.bootstrap.access_components import AccessComponents
from inframeld_backend.shared.infrastructure.resources.database import Database


def create_access_components(
    settings: KratosSettings | None, database: Database
) -> AccessComponents:
    """Wire stateless authentication without network calls or request-shared SQL sessions."""

    if settings is None:
        return AccessComponents(UnavailableHumanSessionAuthenticationService(), None)

    client = ApiClient(Configuration(host=str(settings.public_url).rstrip("/")))

    verifier = KratosBrowserSessionVerifier(FrontendApi(client), settings.authority)

    service = HumanSessionAuthenticationService(verifier, PostgresHumanIdentityLinkReader(database))

    return AccessComponents(service, client)
