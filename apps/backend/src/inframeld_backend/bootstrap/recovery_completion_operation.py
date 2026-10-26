from typing import override

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_result_dto import (
    IdentityRecoveryCleanupResultDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_reconciler import (
    IdentityRecoveryCompletionReconciler,
)
from inframeld_backend.access.application.services.identity_recovery_completion_service import (
    IdentityRecoveryCompletionService,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_proof_reader import (
    PostgresIdentityRecoveryCleanupProofReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_completion_facts_reader import (
    PostgresIdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_identity_recovery_repository import (
    PostgresIdentityRecoveryRepository,
)
from inframeld_backend.access.infrastructure.resources.sqlalchemy_recovery_transaction_manager import (
    SqlAlchemyRecoveryTransactionManager,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_proof_writer import (
    PostgresIdentityRecoveryCleanupProofWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.resources.database import Database


class RecoveryCompletionOperation(IdentityRecoveryCompletionReconciler):
    """Open fresh operation-local resources for each original checklist in a batch."""

    def __init__(
        self,
        database: Database,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        database_timeout_seconds: float = 5,
    ) -> None:
        self._database = database
        self._installation_id = installation_id
        self._authority = authority
        self._database_timeout_seconds = database_timeout_seconds

    @override
    async def reconcile_proof(
        self, *, operation_id: OperationId, covering_operation_id: OperationId | None = None
    ) -> IdentityRecoveryCleanupResultDTO:
        try:
            async with self._database.session() as session:
                service = IdentityRecoveryCompletionService(
                    SqlAlchemyRecoveryTransactionManager(session),
                    PostgresIdentityRecoveryCompletionFactsReader(session),
                    PostgresIdentityRecoveryRepository(session),
                    installation_id=self._installation_id,
                    authority=self._authority,
                    proofs=PostgresIdentityRecoveryCleanupProofReader(
                        session, installation_id=self._installation_id, authority=self._authority
                    ),
                    proof_writer=PostgresIdentityRecoveryCleanupProofWriter(
                        session, installation_id=self._installation_id, authority=self._authority
                    ),
                    database_timeout_seconds=self._database_timeout_seconds,
                )
                return await service.reconcile_proof(
                    operation_id=operation_id, covering_operation_id=covering_operation_id
                )
        except (OperationalError, InterfaceError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None
