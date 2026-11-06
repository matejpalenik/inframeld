from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.grant_recipients_page_facts_dto import (
    GrantRecipientsPageFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class GrantRecipientsFactsReader(Protocol):
    @abstractmethod
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        target: ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO,
        action_id: ActionId,
        eligible_kinds: tuple[PrincipalKind, ...],
        after: PrincipalId | None,
        limit: int,
    ) -> GrantRecipientsPageFactsDTO | None:
        """Observe exact scope/current authority and limit+1 eligible members in one snapshot.

        Apply the supplied catalogue kinds, current membership, active status,
        human coherence/recovery and immutable application binding BEFORE UUID
        position and LIMIT. Return those eligibility observations for application
        verification. Preserve an empty page's authority header. Do not authorize,
        mutate, lock or scan an unbounded candidate set. Bootstrap owns the clean
        request-local session and recognized dependency failures fail closed.
        """
        ...
