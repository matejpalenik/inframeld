from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.create_project_command import (
    CreateProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_creation_result_dto import (
    ProjectCreationResultDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)


class ProjectCreator(Protocol):
    @abstractmethod
    async def create(
        self,
        *,
        access: AccessContextDTO,
        command: CreateProjectCommand,
        context: OperationAdmissionContextDTO,
    ) -> ProjectCreationResultDTO:
        """Own current authorization and one atomic Project creation transaction.

        Find the original Organization-scoped request before treating the expected
        Organization revision as new work. Save name, membership, eighteen grants,
        audit and typed result together. Replays never recreate removed grants.
        """
        ...
