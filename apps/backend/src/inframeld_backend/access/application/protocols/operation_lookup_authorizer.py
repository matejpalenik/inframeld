from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.operation_lookup_authorization_dto import (
    OperationLookupAuthorizationDTO,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)


class OperationLookupAuthorizer(Protocol):
    """Authorize an expected guard from current facts without reading operation history."""

    @abstractmethod
    async def require_authorization(
        self, *, access: AccessContextDTO, request: LookupOriginalOperationQuery
    ) -> OperationLookupAuthorizationDTO:
        """Deny hidden scope, ineligibility or missing exact authority before search.

        Require the original installation and scope. Fixed grant routes retain
        delegation authority. Missing dependencies fail closed. No reservation
        history, provider dispatch or business mutation belongs in this check.
        """
        ...
