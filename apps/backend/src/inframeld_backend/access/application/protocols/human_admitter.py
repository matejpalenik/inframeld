from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)


class HumanAdmitter(Protocol):
    """Admit Bob under Alice's current authority without provisioning resources.

    Own short preliminary and final transactions, with provider verification between
    them. Current actor and recipient admissibility precede original-result replay.
    New admission, audit and replay completion commit together. Already-admitted
    results preserve business and credential state. Replay performs no repairs.
    """

    @abstractmethod
    async def admit(
        self,
        *,
        access: AccessContextDTO,
        command: AdmitHumanCommand,
        context: IdempotencyContextDTO,
    ) -> HumanAdmissionResultDTO: ...
