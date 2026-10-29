import asyncio

from inframeld_backend.access.application.dtos.public_discovery_dto import PublicDiscoveryDTO
from inframeld_backend.access.infrastructure.settings.discovery_settings import DiscoverySettings
from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database


class InstallationDiscoveryResource:
    """Load one immutable public identity snapshot before serving requests."""

    def __init__(self, settings: DiscoverySettings, hydra: HydraSettings) -> None:
        self._settings = settings
        self._hydra = hydra
        self._descriptor: PublicDiscoveryDTO | None = None

    async def startup(self, database: Database) -> None:
        self._descriptor = None
        async with asyncio.timeout(5):
            identity = await PostgresInstallationIdentityReader(database).read()
        self._descriptor = PublicDiscoveryDTO(
            self._settings.public_api_url, self._hydra.issuer.value, identity
        )

    def read(self) -> PublicDiscoveryDTO | None:
        return self._descriptor
