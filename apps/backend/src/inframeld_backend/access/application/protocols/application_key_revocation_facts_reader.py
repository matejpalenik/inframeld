from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_revocation_facts_dto import (
    ApplicationKeyRevocationFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ApplicationKeyRevocationFactsReader(Protocol):
    """Observe one scoped target and current human Revoke authority on the caller transaction.

    Require READ COMMITTED and retain Organization, Project and target-key locks
    through commit. Read database UTC after waits. No Issue delegation or group
    management is required. Original reads disclose only safe historical metadata.
    """

    @abstractmethod
    async def lock_for_revoke(
        self, *, access: AccessContextDTO, command: RevokeApplicationKeyCommand
    ) -> ApplicationKeyRevocationFactsDTO | None: ...

    @abstractmethod
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationKeyRevocationRecordDTO | None: ...
