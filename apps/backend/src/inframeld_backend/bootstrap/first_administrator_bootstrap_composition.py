from collections.abc import AsyncGenerator
from contextlib import ExitStack, asynccontextmanager
from typing import override

from ory_hydra_client.api.o_auth2_api import OAuth2Api
from ory_hydra_client.api_client import ApiClient as HydraApiClient
from ory_hydra_client.configuration import Configuration as HydraConfiguration
from ory_kratos_client.api.identity_api import IdentityApi
from ory_kratos_client.api_client import ApiClient as KratosApiClient
from ory_kratos_client.configuration import Configuration as KratosConfiguration
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.services.first_administrator_bootstrap_fingerprint_service import (
    FirstAdministratorBootstrapFingerprintService,
)
from inframeld_backend.access.application.services.first_administrator_bootstrap_service import (
    FirstAdministratorBootstrapService,
)
from inframeld_backend.access.cli.mappers.first_administrator_bootstrap_mapper import (
    FirstAdministratorBootstrapMapper,
)
from inframeld_backend.access.infrastructure.readers.postgres_first_administrator_bootstrap_facts_reader import (
    PostgresFirstAdministratorBootstrapFactsReader,
)
from inframeld_backend.access.infrastructure.verifiers.hydra_access_token_verifier import (
    HydraAccessTokenVerifier,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_human_identity_verifier import (
    KratosHumanIdentityVerifier,
)
from inframeld_backend.access.infrastructure.writers.postgres_first_administrator_bootstrap_writer import (
    PostgresFirstAdministratorBootstrapWriter,
)
from inframeld_backend.bootstrap.first_administrator_bootstrap_settings import (
    FirstAdministratorBootstrapSettings,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.infrastructure.readers.file_request_fingerprint_key_reader import (
    FileRequestFingerprintKeyReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)


class _BootstrapTransactionManager(TransactionManager):
    """Defer database availability reads until verified proof enters the fixed DB stage."""

    def __init__(self, database: Database, session: AsyncSession) -> None:
        self._database = database
        self._transactions = SqlAlchemyTransactionManager(session)

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        await self._database.startup()
        async with self._transactions.begin():
            yield


async def execute_first_administrator_bootstrap(
    command: BootstrapFirstAdministratorCommand, settings: FirstAdministratorBootstrapSettings
) -> dict[str, object]:
    database = Database(settings.database)
    try:
        with ExitStack() as providers:
            hydra = HydraApiClient(
                HydraConfiguration(
                    host=str(settings.hydra.admin_url).rstrip("/"), retries=0, debug=False
                )
            )
            providers.callback(hydra.rest_client.pool_manager.clear)
            admin_url = settings.kratos.admin_url
            if admin_url is None:
                raise ValueError("The private Kratos API is required.")
            kratos = KratosApiClient(
                KratosConfiguration(host=str(admin_url).rstrip("/"), retries=0, debug=False)
            )
            providers.callback(kratos.rest_client.pool_manager.clear)
            fingerprints = FirstAdministratorBootstrapFingerprintService(
                RequestFingerprintService(
                    FileRequestFingerprintKeyReader(settings.request_fingerprint.key_file).read()
                )
            )
            # Session/engine construction is lazy. The first SQL availability
            # check runs in begin(), after both providers have verified proof.
            async with database.session() as session:
                result = await FirstAdministratorBootstrapService(
                    token_verifier=HydraAccessTokenVerifier(
                        OAuth2Api(hydra), settings.hydra, settings.kratos.authority
                    ),
                    identity_verifier=KratosHumanIdentityVerifier(
                        IdentityApi(kratos), settings.kratos.authority
                    ),
                    transaction_manager=_BootstrapTransactionManager(database, session),
                    bootstrap_facts_reader=PostgresFirstAdministratorBootstrapFactsReader(session),
                    bootstrap_writer=PostgresFirstAdministratorBootstrapWriter(session),
                    bootstrap_fingerprint_service=fingerprints,
                    provider_timeout_seconds=settings.human_authentication.provider_timeout_seconds,
                    total_timeout_seconds=settings.human_authentication.total_timeout_seconds,
                ).bootstrap(command)
                return FirstAdministratorBootstrapMapper.result(result)
    finally:
        await database.shutdown()
