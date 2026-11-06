from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_metadata_dto import (
    ApplicationAccountMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_key_metadata_dto import (
    ApplicationKeyMetadataDTO,
)
from inframeld_backend.access.application.dtos.application_keys_page_dto import (
    ApplicationKeysPageDTO,
)
from inframeld_backend.access.application.queries.list_application_keys_query import (
    ListApplicationKeysQuery,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class ApplicationAccountReader(Protocol):
    """Inspect one authorized account or a bounded page of safe key metadata.

    Recheck current human eligibility and Project membership on every call. Any
    exact account administration action permits account metadata. Key metadata
    needs Issue or Revoke, without issuance delegation or group-management checks.
    This capability grants no mutation authority and exposes no account directory.
    """

    @abstractmethod
    async def get_account(
        self, *, access: AccessContextDTO, project_id: ProjectId, principal_id: PrincipalId
    ) -> ApplicationAccountMetadataDTO: ...

    @abstractmethod
    async def resolve_account(
        self, *, access: AccessContextDTO, project_id: ProjectId, name: ResourceName
    ) -> ApplicationAccountMetadataDTO: ...

    @abstractmethod
    async def list_keys(
        self, *, access: AccessContextDTO, query: ListApplicationKeysQuery
    ) -> ApplicationKeysPageDTO: ...

    @abstractmethod
    async def get_key(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        key_id: ApplicationKeyId,
    ) -> ApplicationKeyMetadataDTO: ...
