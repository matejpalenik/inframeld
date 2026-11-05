from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.human_admitter import HumanAdmitter
from inframeld_backend.access.application.protocols.human_identity_verifier import (
    HumanIdentityVerifier,
)
from inframeld_backend.access.application.services.human_admission_fingerprint_service import (
    HumanAdmissionFingerprintService,
)
from inframeld_backend.access.application.services.human_admission_service import (
    HumanAdmissionService,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.readers.postgres_human_admission_facts_reader import (
    PostgresHumanAdmissionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_admission_result_reader import (
    PostgresHumanAdmissionResultReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_admission_writer import (
    PostgresHumanAdmissionWriter,
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
async def open_human_admission(
    database: Database,
    admission_fingerprint_service: HumanAdmissionFingerprintService,
    identity_verifier: HumanIdentityVerifier | None,
    identity_authority: IdentityAuthority | None,
    identity_timeout_seconds: float,
) -> AsyncGenerator[HumanAdmitter]:
    """Close the request-local session and fail closed without configured verification.

    Bootstrap retains ownership of the verifier and its provider connection pool.
    """
    if identity_verifier is None or identity_authority is None:
        raise DependencyUnavailableError()

    async with database.session() as session:
        yield HumanAdmissionService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            admission_facts_reader=PostgresHumanAdmissionFactsReader(session),
            admission_writer=PostgresHumanAdmissionWriter(session),
            admission_result_reader=PostgresHumanAdmissionResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            admission_fingerprint_service=admission_fingerprint_service,
            identity_verifier=identity_verifier,
            identity_authority=identity_authority,
            identity_timeout_seconds=identity_timeout_seconds,
        )
