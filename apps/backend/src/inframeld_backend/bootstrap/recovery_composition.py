from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.protocols.identity_recovery_notification_handler import (
    IdentityRecoveryNotificationHandler,
)
from inframeld_backend.access.application.services.identity_recovery_admission_service import (
    IdentityRecoveryAdmissionService,
)
from inframeld_backend.access.application.services.identity_recovery_notification_service import (
    IdentityRecoveryNotificationService,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_association_facts_reader import (
    PostgresIdentityRecoveryAssociationFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_identity_recovery_repository import (
    PostgresIdentityRecoveryRepository,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_evidence_writer import (
    PostgresIdentityRecoveryEvidenceWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)


@asynccontextmanager
async def open_recovery_notifications(
    database: Database,
    *,
    installation_id: InstallationId,
    authority: IdentityAuthority,
    database_timeout_seconds: float,
) -> AsyncGenerator[IdentityRecoveryNotificationHandler]:
    try:
        async with database.session() as session:
            yield IdentityRecoveryNotificationService(
                SqlAlchemyTransactionManager(session),
                IdentityRecoveryAdmissionService(
                    PostgresIdentityRecoveryAdmissionWriter(
                        session, installation_id=installation_id, authority=authority
                    )
                ),
                PostgresIdentityRecoveryEvidenceWriter(
                    session, installation_id=installation_id, authority=authority
                ),
                PostgresIdentityRecoveryRepository(session),
                installation_id=installation_id,
                facts=PostgresIdentityRecoveryAssociationFactsReader(
                    session, installation_id=installation_id, authority=authority
                ),
                database_timeout_seconds=database_timeout_seconds,
            )
    except (OperationalError, InterfaceError, SqlAlchemyTimeoutError):
        # A communication failure during commit does not prove that nothing committed.
        raise DependencyUnavailableError() from None
