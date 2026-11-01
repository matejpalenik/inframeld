from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.shared.application.dtos.resource_name_binding_dto import (
    ResourceNameBindingDTO,
)
from inframeld_backend.shared.application.enums.resource_name_kind import ResourceNameKind
from inframeld_backend.shared.application.protocols.resource_name_binding_reader import (
    ResourceNameBindingReader,
)
from inframeld_backend.shared.application.queries.resolve_resource_name_query import (
    ResolveResourceNameQuery,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresProjectNameBindingReader(ResourceNameBindingReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(self, query: ResolveResourceNameQuery) -> tuple[ResourceNameBindingDTO, ...]:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Project bindings require an active caller transaction.")
        if query.kind is not ResourceNameKind.PROJECT or query.scope.project_id is not None:
            return ()
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed != query.scope.installation_id.value:
            return ()
        rows = await self._session.scalars(
            select(ProjectNameReservationRow)
            .where(
                ProjectNameReservationRow.organization_id == query.scope.organization_id.value,
                ProjectNameReservationRow.name == query.name.value,
            )
            .execution_options(populate_existing=True)
        )
        return tuple(
            ResourceNameBindingDTO(
                ResourceNameKind.PROJECT,
                row.project_id,
                query.scope,
                ResourceName(row.name),
                row.binding_revision,
                row.retired,
            )
            for row in rows
        )
