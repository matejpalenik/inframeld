from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_read_facts_dto import (
    ApplicationAccountReadFactsDTO,
)
from inframeld_backend.access.application.dtos.application_keys_facts_dto import (
    ApplicationKeysFactsDTO,
)
from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class ApplicationAccountFactsReader(Protocol):
    """Observe exact account metadata and current human authority without authorizing disclosure."""

    @abstractmethod
    async def read_account(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: PrincipalId | ResourceName,
    ) -> ApplicationAccountReadFactsDTO | None:
        """Read only the specified ID or exact current Name within its Project.

        Preserve retained labels. A retired name never selects another identity.
        Include current membership, recovery, credential and exact administration
        facts from the same statement as the metadata.
        """
        ...

    @abstractmethod
    async def read_keys(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        key_id: ApplicationKeyId | None,
        after: ApplicationKeyId | None,
        limit: int,
    ) -> ApplicationKeysFactsDTO | None:
        """Observe current authority with at most limit+1 UUID-ordered safe keys.

        A key_id selects one exact record, otherwise after selects the next page.
        Keep the authorization header on an empty page. Read no verifier, secret,
        issuance ceiling or document groups. The application decides disclosure.
        """
        ...
