import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import override

from inframeld_backend.access.application.protocols.identity_recovery_cleanup_proof_reader import (
    IdentityRecoveryCleanupProofReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_proof_writer import (
    IdentityRecoveryCleanupProofWriter,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_reconciler import (
    IdentityRecoveryCleanupReconciler,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_reconciler import (
    IdentityRecoveryCompletionReconciler,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class IdentityRecoveryCleanupReconciliationService(IdentityRecoveryCleanupReconciler):
    """Apply at most one bounded page through independent original-completion operations."""

    def __init__(
        self,
        transactions: TransactionManager,
        proofs: IdentityRecoveryCleanupProofReader,
        writer: IdentityRecoveryCleanupProofWriter,
        completions: IdentityRecoveryCompletionReconciler,
        *,
        database_timeout_seconds: float = 5,
        stop_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        self._transactions = transactions
        self._proofs = proofs
        self._writer = writer
        self._completions = completions
        self._database_timeout_seconds = database_timeout_seconds
        self._stop_requested = stop_requested

    @asynccontextmanager
    async def _stage(self) -> AsyncGenerator[None]:
        try:
            async with asyncio.timeout(self._database_timeout_seconds):
                async with self._transactions.begin():
                    yield
        except TimeoutError:
            raise DependencyUnavailableError(
                "Recovery reconciliation exceeded its database deadline."
            ) from None

    @override
    async def reconcile_pending(self, *, limit: int = 25) -> int:
        if isinstance(limit, bool) or not 1 <= limit <= 25:
            raise ValueError("Reconciliation pages contain between one and twenty-five originals.")

        async with self._stage():
            pending = await self._proofs.pending_operations(limit=limit)

        processed = 0
        for source in pending:
            if self._stop_requested():
                break
            async with self._stage():
                proof = await self._proofs.read_proof(source)
                if proof is None:
                    continue
                older = await self._proofs.linked_older(source, limit=max(1, limit - processed))
            targets = (() if proof.checked_at is not None else (source,)) + older
            for target in targets:
                if processed >= limit or self._stop_requested():
                    return processed
                try:
                    await self._completions.reconcile_proof(
                        operation_id=target,
                        covering_operation_id=None if target == source else source,
                    )
                except (ConflictError, DependencyUnavailableError):
                    async with self._stage():
                        await self._writer.defer(
                            source, until=datetime.now(UTC) + timedelta(seconds=15)
                        )
                    break
                processed += 1

            async with self._stage():
                if not await self._proofs.linked_older(source, limit=1):
                    await self._writer.mark_propagated(source)

        return processed
