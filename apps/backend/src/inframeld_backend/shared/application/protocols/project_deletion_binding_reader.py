from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.deletion_recovery_authorization_dto import (
    DeletionRecoveryAuthorizationDTO,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProjectDeletionBindingReader(Protocol):
    @abstractmethod
    async def find(
        self,
        *,
        authorization: DeletionRecoveryAuthorizationDTO,
        query: LookupOriginalOperationQuery,
    ) -> OperationId | None:
        """Match exact original initiator/scope/method/route/key against retained deletion history.

        Require the captured PROJECT_ACTION_USE/delete-project guard and exact
        DELETE route, without changing the original authority. Do not join live
        Project/membership rows or ordinary reservations and their expiry.
        Return no match for
        missing or ambiguous original identity. The shared status reader decides
        owner observation consistency and the independently captured expiry.
        """
        ...
