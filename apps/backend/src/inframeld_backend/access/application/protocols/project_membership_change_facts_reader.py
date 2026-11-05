from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_departure_responsibility_dto import (
    ProjectDepartureResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectMembershipChangeFactsReader(Protocol):
    @abstractmethod
    async def lock_and_load_membership_state(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        principal_id: PrincipalId,
    ) -> ProjectMembershipChangeFactsDTO | None:
        """Lock Organization then Project and reread current facts at READ COMMITTED.

        Require the active caller transaction. Provider work is excluded.
        Lock waits share the operation's existing database budget.
        """
        ...

    @abstractmethod
    async def load_departure_responsibilities(
        self, *, facts: ProjectMembershipChangeFactsDTO, principal_id: PrincipalId
    ) -> tuple[ProjectDepartureResponsibilityDTO, ...]:
        """Observe affected assignments and candidates for a checked fresh departure.

        Require the exact state loaded by this reader in the same coordinated
        transaction. The caller has authorized the operation, reserved new work,
        checked the reviewed revision and validated the human recipient.
        """
        ...
