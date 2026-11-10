import asyncio
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.protocols.deletion_recovery_authorizer import (
    DeletionRecoveryAuthorizer,
)
from inframeld_backend.shared.application.dtos.retained_deletion_status_dto import (
    RetainedDeletionStatusDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    InvalidInputError,
)
from inframeld_backend.shared.application.protocols.deletion_status_lookup import (
    DeletionStatusLookup,
)
from inframeld_backend.shared.application.protocols.original_operation_lookup import (
    OriginalOperationLookup,
)
from inframeld_backend.shared.application.protocols.project_deletion_binding_reader import (
    ProjectDeletionBindingReader,
)
from inframeld_backend.shared.application.queries.get_deletion_status_query import (
    GetDeletionStatusQuery,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class ProjectDeletionLookupService(OriginalOperationLookup):
    def __init__(
        self,
        authorizer: DeletionRecoveryAuthorizer,
        binding_reader: ProjectDeletionBindingReader,
        status_lookup: DeletionStatusLookup,
    ) -> None:
        self._authorizer = authorizer
        self._binding_reader = binding_reader
        self._status_lookup = status_lookup

    @override
    async def lookup(
        self, *, access: AccessContextDTO, query: LookupOriginalOperationQuery
    ) -> RetainedDeletionStatusDTO | UnresolvedOperationDTO:
        if query.expected_authority.family is not OperationLookupAuthorityFamily.PROJECT_DELETION:
            raise InvalidInputError()
        query.expected_authority.require_supported_scope(
            project_id=query.project_id, method=query.method, requested_route=query.requested_route
        )
        try:
            async with asyncio.timeout(5):
                current = await self._authorizer.require_current_human(access=access)
                if current.principal_id != access.actor_principal_id:
                    raise RuntimeError("Deletion recovery authorization changed the current human.")
                if (
                    current.installation_id != query.installation_id
                    or current.organization_id != query.organization_id
                ):
                    return UnresolvedOperationDTO()
                original = await self._binding_reader.find(authorization=current, query=query)
                if original is None:
                    return UnresolvedOperationDTO()
                return await self._status_lookup.lookup(
                    access=access, query=GetDeletionStatusQuery(original)
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None
