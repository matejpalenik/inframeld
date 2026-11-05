from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.services.admitted_work_authorization_service import (
    AdmittedWorkAuthorizationService,
)
from inframeld_backend.access.application.services.project_budget_authorization_service import (
    ProjectBudgetAuthorizationService,
)
from inframeld_backend.access.infrastructure.readers.postgres_admitted_work_facts_reader import (
    PostgresAdmittedWorkFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_budget_facts_reader import (
    PostgresProjectBudgetFactsReader,
)
from inframeld_backend.shared.application.protocols.project_spending_policy_manager import (
    ProjectSpendingPolicyManager,
)
from inframeld_backend.shared.application.protocols.spending_accountant import SpendingAccountant
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.project_spending_policy_fingerprint_service import (
    ProjectSpendingPolicyFingerprintService,
)
from inframeld_backend.shared.application.services.project_spending_policy_service import (
    ProjectSpendingPolicyService,
)
from inframeld_backend.shared.application.services.spending_accounting_service import (
    SpendingAccountingService,
)
from inframeld_backend.shared.infrastructure.readers.postgres_spending_ledger_reader import (
    PostgresSpendingLedgerReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_spending_ledger_writer import (
    PostgresSpendingLedgerWriter,
)


@asynccontextmanager
async def open_spending_accounting(database: Database) -> AsyncGenerator[SpendingAccountant]:
    async with database.session() as session:
        yield SpendingAccountingService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            admitted_work_authorizer=AdmittedWorkAuthorizationService(
                PostgresAdmittedWorkFactsReader(session)
            ),
            job_ownership=PostgresJobStore(session),
            spending_ledger_reader=PostgresSpendingLedgerReader(session),
            spending_ledger_writer=PostgresSpendingLedgerWriter(session),
            project_budget_authorizer=ProjectBudgetAuthorizationService(
                PostgresProjectBudgetFactsReader(session)
            ),
        )


@asynccontextmanager
async def open_project_spending_policy(
    database: Database, spending_policy_fingerprint_service: ProjectSpendingPolicyFingerprintService
) -> AsyncGenerator[ProjectSpendingPolicyManager]:
    async with database.session() as session:
        yield ProjectSpendingPolicyService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            project_budget_authorizer=ProjectBudgetAuthorizationService(
                PostgresProjectBudgetFactsReader(session)
            ),
            spending_ledger_reader=PostgresSpendingLedgerReader(session),
            spending_ledger_writer=PostgresSpendingLedgerWriter(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            spending_policy_fingerprint_service=spending_policy_fingerprint_service,
        )
