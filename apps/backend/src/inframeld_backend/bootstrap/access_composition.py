"""Assemble Access adapters and application services for one API instance."""

from contextlib import ExitStack

from ory_hydra_client.api.o_auth2_api import OAuth2Api
from ory_hydra_client.api_client import ApiClient as HydraApiClient
from ory_hydra_client.configuration import Configuration as HydraConfiguration
from ory_kratos_client.api.frontend_api import FrontendApi
from ory_kratos_client.api.identity_api import IdentityApi
from ory_kratos_client.api_client import ApiClient as KratosApiClient
from ory_kratos_client.configuration import Configuration as KratosConfiguration

from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.services.human_access_token_authentication_service import (
    HumanAccessTokenAuthenticationService,
)
from inframeld_backend.access.application.services.human_session_authentication_service import (
    HumanSessionAuthenticationService,
)
from inframeld_backend.access.application.services.unavailable_human_session_authentication_service import (
    UnavailableHumanSessionAuthenticationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_identity_link_reader import (
    PostgresHumanIdentityLinkReader,
)
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.verifiers.hydra_access_token_verifier import (
    HydraAccessTokenVerifier,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_human_identity_verifier import (
    KratosHumanIdentityVerifier,
)
from inframeld_backend.bootstrap.access_components import AccessComponents
from inframeld_backend.shared.infrastructure.resources.database import Database


def create_access_components(
    kratos_settings: KratosSettings | None,
    hydra_settings: HydraSettings | None,
    database: Database,
) -> AccessComponents:
    """Assemble authentication without provider calls or shared database sessions.

    Retain cleanup responsibility until assembly succeeds. The application then
    owns the returned clients and releases them through its lifespan.
    """
    if kratos_settings is None:
        if hydra_settings is not None:
            raise ValueError("Hydra authentication requires Kratos configuration.")
        return AccessComponents(
            authenticator=UnavailableHumanSessionAuthenticationService(),
            kratos_client=None,
        )

    reader = PostgresHumanIdentityLinkReader(database)

    with ExitStack() as provider_cleanup:
        kratos_client = KratosApiClient(
            KratosConfiguration(
                host=str(kratos_settings.public_url).rstrip("/"),
                retries=0,
                debug=False,
            )
        )
        provider_cleanup.callback(kratos_client.rest_client.pool_manager.clear)

        authenticator = HumanSessionAuthenticationService(
            KratosBrowserSessionVerifier(
                FrontendApi(kratos_client),
                kratos_settings.authority,
            ),
            reader,
        )

        access_token_authenticator: HumanAccessTokenAuthenticator | None = None
        kratos_admin_client: KratosApiClient | None = None
        hydra_client: HydraApiClient | None = None

        if hydra_settings is not None:
            admin_url = kratos_settings.admin_url
            if admin_url is None:
                raise ValueError("Hydra authentication requires the Kratos admin URL.")

            kratos_admin_client = KratosApiClient(
                KratosConfiguration(
                    host=str(admin_url).rstrip("/"),
                    retries=0,
                    debug=False,
                )
            )
            provider_cleanup.callback(kratos_admin_client.rest_client.pool_manager.clear)

            hydra_client = HydraApiClient(
                HydraConfiguration(
                    host=str(hydra_settings.admin_url).rstrip("/"),
                    retries=0,
                    debug=False,
                )
            )
            provider_cleanup.callback(hydra_client.rest_client.pool_manager.clear)

            access_token_authenticator = HumanAccessTokenAuthenticationService(
                HydraAccessTokenVerifier(
                    OAuth2Api(hydra_client),
                    hydra_settings,
                    kratos_settings.authority,
                ),
                KratosHumanIdentityVerifier(
                    IdentityApi(kratos_admin_client),
                    kratos_settings.authority,
                ),
                reader,
            )

        components = AccessComponents(
            authenticator=authenticator,
            kratos_client=kratos_client,
            access_token_authenticator=access_token_authenticator,
            kratos_admin_client=kratos_admin_client,
            hydra_client=hydra_client,
        )
        provider_cleanup.pop_all()
        return components
