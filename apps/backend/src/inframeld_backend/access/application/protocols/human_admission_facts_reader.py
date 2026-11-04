from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_admission_facts_dto import (
    HumanAdmissionFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


class HumanAdmissionFactsReader(Protocol):
    """Read admission observations using the caller's active transaction."""

    @abstractmethod
    async def read_authorization(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
    ) -> OrganizationAccessFactsDTO | None:
        """Read preliminary authority without provider I/O or admission effects."""
        ...

    @abstractmethod
    async def read_for_admission(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        identity: VerifiedHumanIdentityDTO,
    ) -> HumanAdmissionFactsDTO | None:
        """Take the exact identity turn, then exclusive Organization coordination.

        Require READ COMMITTED. Read current installation, actor, exact recipient
        link, generation and recovery facts in statements after their lock waits.
        Keep all waits within the caller's existing database deadline.
        """
        ...
