from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_issuance_facts_dto import (
    ApplicationKeyIssuanceFactsDTO,
)
from inframeld_backend.access.application.dtos.application_key_issuance_record_dto import (
    ApplicationKeyIssuanceRecordDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ApplicationKeyIssuanceFactsReader(Protocol):
    """Observe current issuance facts and safe history on the caller's transaction.

    Require READ COMMITTED and retain Organization, Project and existing-key
    coordination through that transaction. Count parent keys using database UTC
    after waits. Original reads expose neither plaintext nor verifier material.
    """

    @abstractmethod
    async def lock_for_issue(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
    ) -> ApplicationKeyIssuanceFactsDTO | None: ...

    @abstractmethod
    async def read_original(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        issuer_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> ApplicationKeyIssuanceRecordDTO | None: ...
