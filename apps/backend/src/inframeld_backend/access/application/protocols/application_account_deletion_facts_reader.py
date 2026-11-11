from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.delete_application_account_command import (
    DeleteApplicationAccountCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_deletion_facts_dto import (
    ApplicationAccountDeletionFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ApplicationAccountDeletionFactsReader(Protocol):
    """Observe authority and original history in the active READ COMMITTED transaction.

    Hold Org, Project, account and ordered key coordination through commit and
    read database time after waits. Include retired or suspended targets and
    targets without membership so current denial cannot be hidden by filtering.
    """

    @abstractmethod
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, command: DeleteApplicationAccountCommand
    ) -> ApplicationAccountDeletionFactsDTO | None: ...

    @abstractmethod
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationAccountDeletionRecordDTO | None: ...
