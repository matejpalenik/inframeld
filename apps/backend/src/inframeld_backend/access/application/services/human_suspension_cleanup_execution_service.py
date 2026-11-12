import asyncio
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from time import monotonic
from typing import override
from uuid import UUID

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.human_oauth_credential_revoker import (
    HumanOAuthCredentialRevoker,
)
from inframeld_backend.access.application.protocols.human_session_revoker import HumanSessionRevoker
from inframeld_backend.access.application.protocols.human_suspension_cleanup_checkpoint_writer import (
    HumanSuspensionCleanupCheckpointWriter,
)
from inframeld_backend.access.application.protocols.human_suspension_cleanup_claim_writer import (
    HumanSuspensionCleanupClaimWriter,
)
from inframeld_backend.access.application.protocols.human_suspension_cleanup_executor import (
    HumanSuspensionCleanupExecutor,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.shared.application.dtos.human_suspension_job_binding_dto import (
    HumanSuspensionJobBindingDTO,
)
from inframeld_backend.shared.application.enums.human_suspension_cleanup_step import (
    HumanSuspensionCleanupStep as Step,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class HumanSuspensionCleanupExecutionService(HumanSuspensionCleanupExecutor):
    """Advance the three fixed effects of one original suspension cleanup."""

    def __init__(
        self,
        transaction_manager: TransactionManager,
        claim_writer: HumanSuspensionCleanupClaimWriter,
        checkpoint_writer: HumanSuspensionCleanupCheckpointWriter,
        human_session_revoker: HumanSessionRevoker,
        human_o_auth_credential_revoker: HumanOAuthCredentialRevoker,
        *,
        worker_id: UUID,
        provider_timeout_seconds: float = 5,
        database_timeout_seconds: float = 5,
        lease_seconds: float = 60,
        stop_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._claim_writer = claim_writer
        self._checkpoint_writer = checkpoint_writer
        self._human_session_revoker = human_session_revoker
        self._human_o_auth_credential_revoker = human_o_auth_credential_revoker
        self._worker_id = worker_id
        self._provider_timeout_seconds = provider_timeout_seconds
        self._database_timeout_seconds = database_timeout_seconds
        self._lease_seconds = lease_seconds
        self._stop_requested = stop_requested

    @override
    async def execute_once(self) -> bool:
        if self._stop_requested():
            return False
        async with self._stage():
            context = await self._claim_writer.claim_next(
                worker_id=self._worker_id,
                lease_seconds=min(self._lease_seconds, 120),
                work_seconds=7200,
            )
        if context is None:
            return False
        binding = context.binding
        if not isinstance(binding, HumanSuspensionJobBindingDTO):
            raise RuntimeError("A suspension claim must match its original binding.")

        try:
            for step in Step:
                if self._stop_requested():
                    break
                started = monotonic()
                async with self._stage():
                    dispatch = await self._checkpoint_writer.prepare_dispatch(
                        context, worker_id=self._worker_id, step=step
                    )
                if dispatch is None:
                    continue
                if dispatch.identity != binding.identity:
                    raise RuntimeError("Suspension dispatch must match its original identity.")
                # Count the entire short stage against the observed remaining allowance.
                timeout = min(
                    self._provider_timeout_seconds,
                    dispatch.remaining_seconds - (monotonic() - started),
                )
                if timeout <= 0 or self._stop_requested():
                    break
                outcome = await self._dispatch(step, dispatch.identity, timeout)
                async with self._stage():
                    if outcome is State.CONFIRMED:
                        await self._checkpoint_writer.confirm(
                            context, worker_id=self._worker_id, step=step
                        )
                    else:
                        await self._checkpoint_writer.stop_unconfirmed(
                            context, worker_id=self._worker_id, step=step, outcome=outcome
                        )
                if outcome is not State.CONFIRMED:
                    break
        except AccessDeniedError:
            # A lost fence cannot admit another effect or save a late result.
            pass
        return True

    @asynccontextmanager
    async def _stage(self) -> AsyncGenerator[None]:
        try:
            async with asyncio.timeout(self._database_timeout_seconds):
                async with self._transaction_manager.begin():
                    yield
        except TimeoutError:
            raise DependencyUnavailableError(
                "Suspension cleanup database work exceeded its deadline."
            ) from None

    async def _dispatch(
        self, step: Step, identity: VerifiedHumanIdentityDTO, timeout_seconds: float
    ) -> State:
        deadline = monotonic() + timeout_seconds
        try:
            async with asyncio.timeout(timeout_seconds):
                match step:
                    case Step.KRATOS_SESSIONS:
                        state = (
                            await self._human_session_revoker.revoke_sessions(
                                identity, timeout_seconds=timeout_seconds
                            )
                        ).state
                    case Step.HYDRA_CLI_GRANTS:
                        state = (
                            await self._human_o_auth_credential_revoker.revoke_cli_grants(
                                identity.subject, timeout_seconds=timeout_seconds
                            )
                        ).state
                    case Step.HYDRA_REMEMBERED_LOGINS:
                        state = (
                            await self._human_o_auth_credential_revoker.revoke_remembered_logins(
                                identity.subject, timeout_seconds=timeout_seconds
                            )
                        ).state
                return state if monotonic() < deadline else State.UNCERTAIN
        except TimeoutError:
            return State.UNCERTAIN
