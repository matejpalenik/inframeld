from uuid import UUID

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class JobExecutionService:
    """Choose one supported eligible attempt under durable queue coordination."""

    def __init__(
        self,
        transactions: TransactionManager,
        jobs: JobStore,
        *,
        supported_payloads: tuple[tuple[str, int], ...],
        worker_id: UUID,
        lease_seconds: float = 30,
        work_seconds: float = 7200,
    ) -> None:
        self._transactions = transactions
        self._jobs = jobs
        self._supported_payloads = supported_payloads
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._work_seconds = work_seconds

    async def claim_next(self) -> JobAttemptContextDTO | None:
        raise NotImplementedError
