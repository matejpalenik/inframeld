import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.dtos.model_connections_page_dto import (
    ModelConnectionsPageDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.model_connection_read_repository import (
    ModelConnectionReadRepository,
)
from inframeld_backend.access.application.protocols.model_connection_reader import (
    ModelConnectionReader,
)
from inframeld_backend.access.application.services.principal_access_evaluation_service import (
    PrincipalAccessEvaluationService,
)
from inframeld_backend.access.application.value_objects.model_connections_cursor import (
    ModelConnectionsCursor,
)
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policies.project_visibility_policy import (
    ProjectVisibilityPolicy,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class ModelConnectionReadService(ModelConnectionReader):
    def __init__(
        self, transactions: TransactionManager, repository: ModelConnectionReadRepository
    ) -> None:
        self._transactions = transactions
        self._repository = repository

    @override
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, connection_id: ModelConnectionId
    ) -> ModelConnectionDTO:
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                _, facts = await self._require_scope(access, project_id)
                connection = await self._repository.get_visible(facts, project_id, connection_id)
                if connection is None:
                    raise ResourceNotFoundError()
                if (connection.project_id, connection.connection_id) != (project_id, connection_id):
                    raise RuntimeError("Model connection observation changed the exact target.")
                return connection
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @override
    async def list_connections(
        self, access: AccessContextDTO, project_id: ProjectId, limit: int, cursor: str | None
    ) -> ModelConnectionsPageDTO:
        if not 1 <= limit <= 100:
            raise InvalidInputError()
        try:
            position = ModelConnectionsCursor.from_token(cursor) if cursor is not None else None
        except ValueError:
            raise InvalidInputError("The continuation cursor is invalid or incompatible.") from None
        try:
            async with asyncio.timeout(5), self._transactions.begin():
                installation, facts = await self._require_scope(access, project_id)
                if position is not None and (position.installation_id, position.project_id) != (
                    installation,
                    project_id,
                ):
                    raise InvalidInputError("The continuation cursor is invalid or incompatible.")
                after = position.after if position is not None else None
                rows = await self._repository.list_visible(facts, project_id, after, limit + 1)
                if len(rows) > limit + 1:
                    raise RuntimeError("Model connection observation exceeded its page bound.")
                for row in rows:
                    if row.project_id != project_id or (
                        after is not None and row.connection_id.value <= after.value
                    ):
                        raise RuntimeError(
                            "Model connection observation changed its position or scope."
                        )
                    after = row.connection_id
                items = rows[:limit]
                next_cursor = (
                    ModelConnectionsCursor(
                        installation, project_id, items[-1].connection_id
                    ).to_token()
                    if len(rows) > limit
                    else None
                )
                return ModelConnectionsPageDTO(items, next_cursor)
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @override
    async def list_usage(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
        limit: int,
        cursor: str | None,
    ) -> None:
        if not 1 <= limit <= 100:
            raise InvalidInputError()
        await self.get(access, project_id, connection_id)
        if cursor is not None:
            raise InvalidInputError("The continuation cursor is invalid or incompatible.")

    async def _require_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO]:
        scope = await self._repository.lock_scope(access, project_id)
        if scope is None:
            raise ResourceNotFoundError()
        _, facts = scope
        if facts.principal.id != access.actor_principal_id:
            raise RuntimeError("Model connection observation changed the actor.")
        eligibility = PrincipalAccessEvaluationService.evaluate(
            access=access,
            principal=facts.principal,
            has_pending_recovery=facts.has_pending_recovery,
            oauth_credential_facts=facts.oauth_credential_facts,
            application_key_facts=facts.application_key_facts,
        )
        PrincipalAccessEvaluationService.require_current_credential(
            access=access, principal_access=eligibility
        )
        if not (
            PrincipalAccessPolicy.may_use_product(eligibility)
            and ProjectVisibilityPolicy.may_view_project(
                principal_status=facts.principal.status,
                project_status=facts.project_status,
                is_project_member=facts.is_project_member,
            )
        ):
            raise ResourceNotFoundError()
        return scope
