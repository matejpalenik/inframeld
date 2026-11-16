from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.model_dispatch_credential_service import (
    ModelDispatchCredentialService,
)
from inframeld_backend.access.application.services.project_budget_authorization_service import (
    ProjectBudgetAuthorizationService,
)
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_model_dispatch_credential_reader import (
    PostgresModelDispatchCredentialReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_budget_facts_reader import (
    PostgresProjectBudgetFactsReader,
)
from inframeld_backend.shared.application.protocols.model_embedding_adapter import (
    ModelEmbeddingAdapter,
)
from inframeld_backend.shared.application.services.model_embedding_gateway import (
    ModelDispatchPhase,
    ModelEmbeddingGateway,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.services.spending_accounting_service import (
    SpendingAccountingService,
)
from inframeld_backend.shared.infrastructure.readers.postgres_spending_ledger_reader import (
    PostgresSpendingLedgerReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.repositories.postgres_model_dispatch_issuance_repository import (
    PostgresModelDispatchIssuanceRepository,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_spending_ledger_writer import (
    PostgresSpendingLedgerWriter,
)


def build_model_embedding_gateway(
    database: Database,
    adapter: ModelEmbeddingAdapter,
    destinations: ModelConnectionDestinationPolicy,
    fingerprints: RequestFingerprintService,
) -> ModelEmbeddingGateway:
    """Assemble the private gateway with a fresh session for each database phase."""

    @asynccontextmanager
    async def phase() -> AsyncGenerator[ModelDispatchPhase]:
        async with database.session() as session:
            transactions = SqlAlchemyTransactionManager(session)
            jobs = PostgresJobStore(session)
            authorization = AdmittedWorkAuthorizationService(
                PostgresAdmittedWorkFactsReader(session)
            )
            yield (
                transactions,
                ModelDispatchCredentialService(
                    authorization,
                    jobs,
                    PostgresModelDispatchCredentialReader(session),
                    destinations,
                ),
                SpendingAccountingService(
                    transaction_manager=transactions,
                    admitted_work_authorizer=authorization,
                    job_ownership=jobs,
                    spending_ledger_reader=PostgresSpendingLedgerReader(session),
                    spending_ledger_writer=PostgresSpendingLedgerWriter(session),
                    project_budget_authorizer=ProjectBudgetAuthorizationService(
                        PostgresProjectBudgetFactsReader(session)
                    ),
                ),
                PostgresModelDispatchIssuanceRepository(session, jobs),
            )

    return ModelEmbeddingGateway(phase, adapter, fingerprints)
