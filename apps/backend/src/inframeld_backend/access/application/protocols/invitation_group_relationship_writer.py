from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)


class InvitationGroupRelationshipWriter(Protocol):
    @abstractmethod
    async def apply_invitation_relationship(
        self,
        *,
        binding: InvitationActivationBindingDTO,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        after: AccessGroupRelationships,
    ) -> int:
        """Apply a promised member or manager transition under the real pending binding.

        The caller supplies the native domain transition and current recipient
        prerequisites. Share the native checked rows, preserve no-op attribution
        and per-transition revision, and flush before dependent observations."""
        ...
