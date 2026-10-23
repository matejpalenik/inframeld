from datetime import UTC, datetime
from typing import override

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_result_dto import (
    IdentityRecoveryCleanupResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_completion_facts_dto import (
    IdentityRecoveryCompletionFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_recorder import (
    IdentityRecoveryCleanupRecorder,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_facts_reader import (
    IdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_repository import (
    IdentityRecoveryRepository,
)
from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.errors.identity_recovery_errors import (
    IdentityRecoveryTransitionError,
)
from inframeld_backend.access.domain.policies.identity_recovery_release_policy import (
    IdentityRecoveryReleasePolicy,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class IdentityRecoveryCompletionService(IdentityRecoveryCleanupRecorder):
    def __init__(
        self,
        transactions: TransactionManager,
        facts: IdentityRecoveryCompletionFactsReader,
        recoveries: IdentityRecoveryRepository,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
    ) -> None:
        self._transactions = transactions
        self._facts = facts
        self._recoveries = recoveries
        self._installation_id = installation_id
        self._authority = authority

    @override
    async def record_cleanup(
        self,
        *,
        event: IdentityRecoveryEventDTO,
        kratos_outcome: IdentityRecoveryCleanupState | None = None,
        hydra_outcome: IdentityRecoveryCleanupState | None = None,
    ) -> IdentityRecoveryCleanupResultDTO:
        if (
            kratos_outcome is None and hydra_outcome is None
        ) or IdentityRecoveryCleanupState.PENDING in (kratos_outcome, hydra_outcome):
            raise InvalidInputError("Supply at least one non-pending provider cleanup outcome.")

        if event.identity.authority != self._authority:
            raise ConflictError("The recovery event does not match the configured provider.")

        async with self._transactions.begin():
            try:
                facts = await self._facts.read(
                    installation_id=self._installation_id,
                    authority=self._authority,
                    flow_id=event.flow_id,
                )
            except ResourceNotFoundError as error:
                raise ConflictError(
                    "Cannot record cleanup results because the recovery record was not found."
                ) from error

            stored_event = facts.admission.event

            if (
                facts.installation_id != self._installation_id
                or stored_event.identity.authority != self._authority
                or stored_event.flow_id != event.flow_id
            ):
                raise RuntimeError("Recovery facts do not match the requested scope.")

            if stored_event != event:
                raise ConflictError("The recovery flow is already bound to another event.")

            try:
                recovery = await self._recoveries.get(
                    installation_id=facts.installation_id,
                    authority=stored_event.identity.authority,
                    flow_id=stored_event.flow_id,
                )
            except ResourceNotFoundError as error:
                raise ConflictError(
                    "Recovery completion requires an existing admission."
                ) from error

            if (
                recovery.identity
                != (facts.installation_id, stored_event.identity.authority, stored_event.flow_id)
                or recovery.subject != stored_event.identity.subject
            ):
                raise RuntimeError("The loaded recovery does not match its original admission.")

            if recovery.is_released:
                return self._to_result(recovery, facts)

            try:
                if kratos_outcome is not None:
                    recovery.record_kratos_cleanup(kratos_outcome)
                if hydra_outcome is not None:
                    recovery.record_hydra_cleanup(hydra_outcome)
            except IdentityRecoveryTransitionError as error:
                raise ConflictError(
                    "The cleanup outcome conflicts with confirmed recovery progress."
                ) from error

            if IdentityRecoveryReleasePolicy.may_release(
                recovery=recovery, principal=facts.principal
            ):
                recovery.release_product_block(at=datetime.now(UTC))

            await self._recoveries.save(recovery)

            return self._to_result(recovery, facts)

    @staticmethod
    def _to_result(
        recovery: IdentityRecovery, facts: IdentityRecoveryCompletionFactsDTO
    ) -> IdentityRecoveryCleanupResultDTO:
        return IdentityRecoveryCleanupResultDTO(
            operation_id=facts.admission.operation_id,
            kratos_cleanup_state=recovery.kratos_cleanup_state,
            hydra_cleanup_state=recovery.hydra_cleanup_state,
            released_at=recovery.released_at,
            has_other_pending_recovery=facts.has_other_pending_recovery,
        )
