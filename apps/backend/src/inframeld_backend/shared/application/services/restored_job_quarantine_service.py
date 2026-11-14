from inframeld_backend.shared.application.commands.restored_job_quarantine_command import (
    RestoredJobQuarantineCommand,
)
from inframeld_backend.shared.application.dtos.restored_job_quarantine_result_dto import (
    RestoredJobQuarantineResultDTO,
)
from inframeld_backend.shared.application.enums.restored_job_quarantine_intent import (
    RestoredJobQuarantineIntent,
)
from inframeld_backend.shared.application.protocols.restored_job_quarantine_repository import (
    RestoredJobQuarantineRepository,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class RestoredJobQuarantineService:
    """Commit a reviewed one-way quarantine before returning its result."""

    def __init__(
        self,
        transaction_manager: TransactionManager,
        restored_job_quarantine_repository: RestoredJobQuarantineRepository,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._restored_job_quarantine_repository = restored_job_quarantine_repository

    async def execute(
        self, command: RestoredJobQuarantineCommand
    ) -> RestoredJobQuarantineResultDTO:
        async with self._transaction_manager.begin():
            observed = await self._restored_job_quarantine_repository.observe_restored_job(command)
            if command.intent is RestoredJobQuarantineIntent.QUARANTINE:
                observed = await self._restored_job_quarantine_repository.quarantine_restored_job(
                    command, observed
                )
            result = RestoredJobQuarantineResultDTO.from_snapshot(observed)
        return result
