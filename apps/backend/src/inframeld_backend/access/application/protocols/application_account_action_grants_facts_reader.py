from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_action_grants_page_facts_dto import (
    ApplicationAccountActionGrantsPageFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ApplicationAccountActionGrantsFactsReader(Protocol):
    @abstractmethod
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> ApplicationAccountActionGrantsPageFactsDTO | None:
        """Observe current authority and at most limit+1 stored rows in one SQL snapshot.

        Filter scope and action before UUID position and limit. Retain authority
        facts for empty pages. Do not authorize, lock, write or hide suspended
        recipients. Bootstrap owns the clean request-local session lifetime.
        """
        ...
