from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_lifecycle_facts_dto import (
    HumanLifecycleFactsDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class HumanLifecycleFactsReader(Protocol):
    """Observe current actor and exact stable target without provider I/O.

    lock_for_change requires the caller READ COMMITTED transaction, takes the
    target identity turn before Organization UPDATE and rereads after waits.
    The original five-second stage includes all waits. Never initialize versions.
    """

    @abstractmethod
    async def read_authorization(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        action_id: ActionId,
    ) -> HumanLifecycleFactsDTO | None: ...

    @abstractmethod
    async def lock_for_change(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        principal_id: PrincipalId,
        action_id: ActionId,
        identity: VerifiedHumanIdentityDTO,
    ) -> HumanLifecycleFactsDTO | None: ...
