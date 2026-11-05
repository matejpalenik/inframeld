from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.project_action_grant_change_result_dto import (
    ProjectActionGrantChangeResultDTO,
)


class ProjectActionGrantResultWriter(Protocol):
    @abstractmethod
    async def save(
        self,
        result: ProjectActionGrantChangeResultDTO,
        *,
        before_revision: int,
        before_can_grant: bool | None,
    ) -> None:
        """Save original result beside its same-transaction completed reservation.

        Capture no-op facts and original status too. Never overwrite a result,
        commit, infer current permission or depend on a removable grant row.
        Persistence and cancellation failures propagate for whole rollback.
        """
        ...
