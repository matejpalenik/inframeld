from dataclasses import dataclass

from ory_hydra_client.api_client import ApiClient as HydraApiClient
from ory_kratos_client.api_client import ApiClient as KratosApiClient

from inframeld_backend.access.application.protocols.human_access_token_authenticator import (
    HumanAccessTokenAuthenticator,
)
from inframeld_backend.access.application.protocols.human_oauth_consent_handler import (
    HumanOAuthConsentHandler,
)
from inframeld_backend.access.application.protocols.human_session_authenticator import (
    HumanSessionAuthenticator,
)


@dataclass(frozen=True, slots=True)
class AccessComponents:
    """Expose human authentication, optional consent and their owned clients.

    The existing authenticator and kratos_client fields retain their browser
    roles. Bearer authentication is absent when Hydra is not configured.
    """

    authenticator: HumanSessionAuthenticator
    kratos_client: KratosApiClient | None
    access_token_authenticator: HumanAccessTokenAuthenticator | None = None
    kratos_admin_client: KratosApiClient | None = None
    hydra_client: HydraApiClient | None = None
    oauth_consent_handler: HumanOAuthConsentHandler | None = None
