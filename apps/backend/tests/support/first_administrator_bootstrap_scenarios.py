"""Exercise actual claim persistence after controlled provider verification."""

from dataclasses import dataclass
from typing import override
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.bootstrap_first_administrator_command import (
    BootstrapFirstAdministratorCommand,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_access_token_verifier import (
    HumanAccessTokenVerifier,
)
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.first_administrator_bootstrap_fingerprint_service import (
    FirstAdministratorBootstrapFingerprintService,
)
from inframeld_backend.access.application.services.first_administrator_bootstrap_service import (
    FirstAdministratorBootstrapService,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.readers.postgres_first_administrator_bootstrap_facts_reader import (
    PostgresFirstAdministratorBootstrapFactsReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_first_administrator_bootstrap_writer import (
    PostgresFirstAdministratorBootstrapWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)


class MockBootstrapTokenVerifier(HumanAccessTokenVerifier):
    def __init__(self, binding: HumanOAuthCredentialBindingDTO) -> None:
        self._binding = binding

    @override
    async def verify(
        self, credential: HumanAccessTokenCredential, *, timeout_seconds: float
    ) -> HumanOAuthCredentialBindingDTO | None:
        return self._binding


class MockBootstrapIdentityVerifier(HumanIdentityVerifier):
    @override
    async def verify(
        self, identity: VerifiedHumanIdentityDTO, *, timeout_seconds: float
    ) -> VerifiedHumanIdentityDTO | None:
        return identity


@dataclass(frozen=True, slots=True)
class FirstAdministratorScenarioDTO:
    binding: HumanOAuthCredentialBindingDTO
    command: BootstrapFirstAdministratorCommand


async def bootstrap_scenario(
    database: Database,
    *,
    identity: VerifiedHumanIdentityDTO | None = None,
    operation: str = "first-claim",
) -> FirstAdministratorScenarioDTO:
    identity = identity or VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
    )
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    binding = HumanOAuthCredentialBindingDTO(identity, state.installation_id, state.version)
    return FirstAdministratorScenarioDTO(
        binding,
        BootstrapFirstAdministratorCommand(
            binding.installation_id,
            OperationId(operation),
            0,
            UUID(identity.subject.value),
            "Host operator",
            "First admission",
            HumanAccessTokenCredential("controlled-provider-proof"),
        ),
    )


def bootstrap_service(
    session: AsyncSession, binding: HumanOAuthCredentialBindingDTO
) -> FirstAdministratorBootstrapService:
    return FirstAdministratorBootstrapService(
        token_verifier=MockBootstrapTokenVerifier(binding),
        identity_verifier=MockBootstrapIdentityVerifier(),
        transaction_manager=SqlAlchemyTransactionManager(session),
        bootstrap_facts_reader=PostgresFirstAdministratorBootstrapFactsReader(session),
        bootstrap_writer=PostgresFirstAdministratorBootstrapWriter(session),
        bootstrap_fingerprint_service=FirstAdministratorBootstrapFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"k" * 32))
        ),
    )
