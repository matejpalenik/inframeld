from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.protocols.human_restorer import HumanRestorer
from inframeld_backend.access.application.protocols.human_suspender import HumanSuspender
from inframeld_backend.access.application.services.human_lifecycle_fingerprint_service import (
    HumanLifecycleFingerprintService,
)
from inframeld_backend.access.application.services.human_restoration_service import (
    HumanRestorationService,
)
from inframeld_backend.access.application.services.human_suspension_service import (
    HumanSuspensionService,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_lifecycle_facts_reader import (
    PostgresHumanLifecycleFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_lifecycle_result_reader import (
    PostgresHumanLifecycleResultReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_lifecycle_writer import (
    PostgresHumanLifecycleWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_human_suspension(
    database: Database, fingerprints: HumanLifecycleFingerprintService
) -> AsyncGenerator[HumanSuspender]:
    """Bind suspension to one request-local session without requiring provider verification."""
    async with database.session() as session:
        yield HumanSuspensionService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            lifecycle_facts_reader=PostgresHumanLifecycleFactsReader(session),
            lifecycle_writer=PostgresHumanLifecycleWriter(session),
            lifecycle_result_reader=PostgresHumanLifecycleResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            lifecycle_fingerprint_service=fingerprints,
        )


@asynccontextmanager
async def open_human_restoration(
    database: Database,
    fingerprints: HumanLifecycleFingerprintService,
    identity_verifier: HumanIdentityVerifier | None,
) -> AsyncGenerator[HumanRestorer]:
    """Bind restoration to a local session and the configured bootstrap-owned verifier."""
    if identity_verifier is None:
        raise DependencyUnavailableError()
    async with database.session() as session:
        yield HumanRestorationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            lifecycle_facts_reader=PostgresHumanLifecycleFactsReader(session),
            lifecycle_writer=PostgresHumanLifecycleWriter(session),
            lifecycle_result_reader=PostgresHumanLifecycleResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            lifecycle_fingerprint_service=fingerprints,
            identity_verifier=identity_verifier,
        )
