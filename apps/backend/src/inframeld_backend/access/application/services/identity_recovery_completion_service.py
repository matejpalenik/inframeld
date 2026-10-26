import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import override

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_proof_dto import (
    IdentityRecoveryCleanupProofDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_result_dto import (
    IdentityRecoveryCleanupResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_completion_facts_dto import (
    IdentityRecoveryCompletionFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_proof_reader import (
    IdentityRecoveryCleanupProofReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_proof_writer import (
    IdentityRecoveryCleanupProofWriter,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_recorder import (
    IdentityRecoveryCleanupRecorder,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_facts_reader import (
    IdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_reconciler import (
    IdentityRecoveryCompletionReconciler,
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
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class IdentityRecoveryCompletionService(
    IdentityRecoveryCleanupRecorder, IdentityRecoveryCompletionReconciler
):
    def __init__(
        self,
        transactions: TransactionManager,
        facts: IdentityRecoveryCompletionFactsReader,
        recoveries: IdentityRecoveryRepository,
        *,
        proofs: IdentityRecoveryCleanupProofReader,
        proof_writer: IdentityRecoveryCleanupProofWriter,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        database_timeout_seconds: float = 5,
    ) -> None:
        self._database_timeout_seconds = database_timeout_seconds
        self._proofs = proofs
        self._proof_writer = proof_writer
        self._transactions = transactions
        self._facts = facts
        self._recoveries = recoveries
        self._installation_id = installation_id
        self._authority = authority

    @override
    async def reconcile_proof(
        self, *, operation_id: OperationId, covering_operation_id: OperationId | None = None
    ) -> IdentityRecoveryCleanupResultDTO:
        async with self._proof_stage():
            original = await self._proofs.read_admission(operation_id)
            if original.operation_id != operation_id:
                raise RuntimeError("Proof facts do not match the original operation.")

            facts = await self._read_checked_facts(original.event)
            if facts.admission.operation_id != operation_id:
                raise RuntimeError("Completion facts changed the original operation.")

            source_id = covering_operation_id or operation_id
            proof = await self._proofs.read_proof(source_id)
            if proof is None:
                raise ConflictError("Recovery completion requires saved cleanup proof.")

            if proof.admission.operation_id != source_id:
                raise RuntimeError("Cleanup proof changed the selected original operation.")

            self._require_complete_proof(proof, facts)
            source = proof.source_admission.operation_id
            if source != operation_id and not await self._proofs.is_linked(source, operation_id):
                raise ConflictError("The newer recovery does not cover this checklist.")

            if covering_operation_id is not None and covering_operation_id != operation_id:
                if source != covering_operation_id:
                    raise ConflictError(
                        "Only original complete evidence may cover older recoveries."
                    )
                await self._proof_writer.apply_to_covered(
                    proof, facts.admission, at=datetime.now(UTC)
                )

            result = await self._record(
                facts,
                IdentityRecoveryCleanupState.CONFIRMED,
                IdentityRecoveryCleanupState.CONFIRMED,
            )
            await self._proof_writer.record_checked(
                operation_id, at=datetime.now(UTC), released=result.released_at is not None
            )
            return result

    @asynccontextmanager
    async def _proof_stage(self) -> AsyncGenerator[None]:
        try:
            async with asyncio.timeout(self._database_timeout_seconds):
                async with self._transactions.begin():
                    yield
        except TimeoutError:
            raise DependencyUnavailableError(
                "Recovery completion exceeded its database deadline."
            ) from None

    @staticmethod
    def _require_complete_proof(
        proof: IdentityRecoveryCleanupProofDTO, facts: IdentityRecoveryCompletionFactsDTO
    ) -> None:
        if (
            proof.installation_id != facts.installation_id
            or proof.source_admission.event.identity != facts.admission.event.identity
            or proof.admission.event.identity != facts.admission.event.identity
        ):
            raise RuntimeError("Cleanup proof does not match the original identity.")

        if not (
            proof.has_password_saved_receipt
            and proof.source_kratos_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
            and proof.has_cli_confirmation
            and proof.has_login_confirmation
        ):
            raise ConflictError("Recovery completion requires all original cleanup evidence.")

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
            facts = await self._read_checked_facts(event)
            return await self._record(facts, kratos_outcome, hydra_outcome)

    async def _read_checked_facts(
        self, event: IdentityRecoveryEventDTO
    ) -> IdentityRecoveryCompletionFactsDTO:
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

        if facts.credential_version is None:
            raise DependencyUnavailableError("Recovery credential state is unavailable.")

        return facts

    async def _record(
        self,
        facts: IdentityRecoveryCompletionFactsDTO,
        kratos_outcome: IdentityRecoveryCleanupState | None,
        hydra_outcome: IdentityRecoveryCleanupState | None,
    ) -> IdentityRecoveryCleanupResultDTO:
        stored_event = facts.admission.event
        try:
            recovery = await self._recoveries.get(
                installation_id=facts.installation_id,
                authority=stored_event.identity.authority,
                flow_id=stored_event.flow_id,
            )
        except ResourceNotFoundError as error:
            raise ConflictError("Recovery completion requires an existing admission.") from error

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

        if IdentityRecoveryReleasePolicy.may_release(recovery=recovery, principal=facts.principal):
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
