from typing import override

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_binding_dto import (
    InvitationActivationBindingDTO,
)
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_facts_dto import (
    ModelConnectionGrantFactsDTO,
)
from inframeld_backend.access.application.protocols.invitation_model_connection_grant_writer import (
    InvitationModelConnectionGrantWriter,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.postgres_invitation_binding_reader import (
    PostgresInvitationBindingReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_model_connection_action_grant_writer import (
    PostgresModelConnectionActionGrantWriter,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError


class PostgresInvitationModelConnectionGrantWriter(InvitationModelConnectionGrantWriter):
    """Bind the shared native write to the exact pending invitation and recipient."""

    def __init__(self, session: AsyncSession) -> None:
        self._bindings = PostgresInvitationBindingReader(session)
        self._assignments = PostgresModelConnectionActionGrantWriter(session)

    @override
    async def apply_invitation_grant(
        self,
        binding: InvitationActivationBindingDTO,
        facts: ModelConnectionGrantFactsDTO,
        recipient: PrincipalId,
        after: ActionGrantState,
    ) -> int:
        if after.can_grant is None:
            raise ConflictError("An invitation must assign an explicit grant level.")
        await self._bindings.require_assignment_binding(
            binding=binding,
            principal_id=recipient,
            organization_id=facts.organization_id,
            issuer_principal_id=facts.actor.principal.id,
            installation_id=facts.installation_id,
            intent=InvitationActionGrantIntentDTO(
                InvitationModelConnectionTargetDTO(facts.model_connection_id.value),
                ActionId(facts.action.value),
                after.can_grant,
            ),
        )
        return await self._assignments.apply_assignment(
            facts, recipient, after, binding.operation_id
        )
