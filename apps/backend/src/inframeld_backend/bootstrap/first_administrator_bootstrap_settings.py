from typing import Self

from pydantic import Field, model_validator

from inframeld_backend.access.infrastructure.settings.human_authentication_settings import (
    HumanAuthenticationSettings,
)
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.bootstrap.maintenance_application_settings import (
    MaintenanceApplicationSettings,
)
from inframeld_backend.shared.infrastructure.settings.request_fingerprint_settings import (
    RequestFingerprintSettings,
)


class FirstAdministratorBootstrapSettings(MaintenanceApplicationSettings):
    """Require private proof configuration only for the first-administrator mode."""

    kratos: KratosSettings
    hydra: HydraSettings
    request_fingerprint: RequestFingerprintSettings
    human_authentication: HumanAuthenticationSettings = Field(
        default_factory=HumanAuthenticationSettings
    )

    @model_validator(mode="after")
    def _require_private_identity_api(self) -> Self:
        if self.kratos.admin_url is None:
            raise ValueError("Bootstrap requires the configured private Kratos API.")
        return self
