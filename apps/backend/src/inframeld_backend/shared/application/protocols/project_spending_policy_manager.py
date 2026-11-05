from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.change_project_spending_policy_command import (
    ChangeProjectSpendingPolicyCommand,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_result_dto import (
    ProjectSpendingPolicyResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_projection_dto import SpendingProjectionDTO
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod


class ProjectSpendingPolicyManager(Protocol):
    """Inspect permitted accounting and change policy through current human authority."""

    @abstractmethod
    async def change_limit(
        self,
        *,
        access: AccessContextDTO,
        command: ChangeProjectSpendingPolicyCommand,
        context: IdempotencyContextDTO,
    ) -> ProjectSpendingPolicyResultDTO: ...

    @abstractmethod
    async def inspect(
        self, *, access: AccessContextDTO, project_id: ProjectId, period: SpendingPeriod
    ) -> SpendingProjectionDTO: ...
