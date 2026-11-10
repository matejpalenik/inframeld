from typing import override

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.deletion_recovery_authorization_dto import (
    DeletionRecoveryAuthorizationDTO,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.project_deletion_binding_reader import (
    ProjectDeletionBindingReader,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.mappers.postgres_deletion_status_mapper import (
    PostgresDeletionStatusMapper,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)


class PostgresProjectDeletionBindingReader(ProjectDeletionBindingReader):
    """Read exact retained identity without current product rows or ordinary replay expiry.

    The enclosing lookup service owns its existing five-second observation
    deadline. Owner consistency and independently captured retention stay with
    the retained status reader, never with this original-identity match.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def find(
        self,
        *,
        authorization: DeletionRecoveryAuthorizationDTO,
        query: LookupOriginalOperationQuery,
    ) -> OperationId | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Project deletion recovery requires the active caller transaction.")
        if (
            query.project_id is None
            or query.expected_authority.family
            is not OperationLookupAuthorityFamily.PROJECT_DELETION
            or query.expected_authority.action_id.value != ProjectAction.DELETE_PROJECT.value
        ):
            return None
        binding = DeletionStatusBindingRow
        try:
            rows = (
                await self._session.scalars(
                    select(binding)
                    .where(
                        binding.installation_id == authorization.installation_id.value,
                        binding.installation_id == query.installation_id.value,
                        binding.organization_id == authorization.organization_id.value,
                        binding.organization_id == query.organization_id.value,
                        binding.initiator_principal_id == authorization.principal_id.value,
                        binding.project_id == query.project_id.value,
                        binding.method == query.method,
                        binding.method == HttpMethod.DELETE.value,
                        binding.requested_route == query.requested_route,
                        binding.requested_route == f"/v1/projects/{query.project_id.value}",
                        binding.request_key == query.key.value,
                        binding.authority_family
                        == OperationLookupAuthorityFamily.PROJECT_ACTION_USE.value,
                        binding.action_id == ProjectAction.DELETE_PROJECT.value,
                    )
                    .limit(2)
                    .execution_options(populate_existing=True, autoflush=False)
                )
            ).all()
            if len(rows) != 1:
                return None
            return PostgresDeletionStatusMapper.to_binding(rows[0]).operation_id
        except (OperationalError, SqlAlchemyTimeoutError, TypeError, ValueError, LookupError):
            raise DependencyUnavailableError() from None
