import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grants_page_dto import (
    ModelConnectionGrantsPageDTO,
)
from inframeld_backend.access.application.protocols.model_connection_grant_read_repository import (
    ModelConnectionGrantReadRepository,
)
from inframeld_backend.access.application.protocols.model_connection_grants_reader import (
    ModelConnectionGrantsReader,
)
from inframeld_backend.access.application.services.model_connection_grant_change_service import (
    ModelConnectionGrantChangeService,
)
from inframeld_backend.access.application.value_objects.access_action_grants_cursor import (
    AccessActionGrantsCursor,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


class ModelConnectionGrantsReadService(ModelConnectionGrantsReader):
    def __init__(
        self,
        transactions: TransactionManager,
        repository: ModelConnectionGrantReadRepository,
    ) -> None:
        self._transactions = transactions
        self._repository = repository

    @override
    async def list_grants(
        self,
        access: AccessContextDTO,
        connection_id: ModelConnectionId,
        action: ModelConnectionAction,
        limit: int,
        cursor: str | None,
    ) -> ModelConnectionGrantsPageDTO:
        if not 1 <= limit <= 100:
            raise InvalidInputError()
        try:
            position = AccessActionGrantsCursor.from_token(cursor) if cursor is not None else None
        except ValueError:
            raise InvalidInputError("The continuation cursor is invalid or incompatible.") from None
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                facts = await self._repository.lock_for_read(access, connection_id, action)
                if facts is None:
                    raise ResourceNotFoundError()
                if (
                    facts.model_connection_id != connection_id
                    or facts.action is not action
                    or facts.actor.principal.id != access.actor_principal_id
                    or facts.actor.principal.organization_id != facts.organization_id
                ):
                    raise RuntimeError("Grant observations changed the target or reader.")
                ModelConnectionGrantChangeService.require_authority(access, facts)
                target = ModelConnectionGrantTargetDTO(facts.project_id, connection_id)
                action_id = ActionId(action.value)
                if position is not None and (
                    position.installation_id,
                    position.organization_id,
                    position.target,
                    position.action_id,
                ) != (facts.installation_id, facts.organization_id, target, action_id):
                    raise InvalidInputError("The continuation cursor is invalid or incompatible.")
                after = position.after if position is not None else None
                rows = await self._repository.list_assignments(facts, after, limit + 1)
                if len(rows) > limit + 1:
                    raise RuntimeError("Grant observation exceeded the page bound.")
                for row in rows:
                    if after is not None and row.recipient_id.value <= after.value:
                        raise RuntimeError("Grant observation changed the recipient order.")
                    after = row.recipient_id
                items = rows[:limit]
                next_cursor = (
                    AccessActionGrantsCursor(
                        facts.installation_id,
                        facts.organization_id,
                        target,
                        action_id,
                        items[-1].recipient_id,
                    ).to_token()
                    if len(rows) > limit
                    else None
                )
                return ModelConnectionGrantsPageDTO(items, next_cursor)
        except TimeoutError:
            raise DependencyUnavailableError() from None
