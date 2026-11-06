from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_group_action_grant_change_result_dto import (
    AccessGroupActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_management_facts_dto import (
    AccessGroupGrantManagementFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class AccessGroupActionGrantWriter(Protocol):
    @abstractmethod
    async def save_change(
        self,
        *,
        facts: AccessGroupGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None:
        """Persist the checked exact transition, one revision and required audit atomically.

        The caller owns coordination and transaction lifetime. No-op does not
        advance revision or append change audit. Reject changed before-values,
        scope or exhausted revision. Never commit, authorize or retry here.
        """
        ...

    @abstractmethod
    async def save_result(
        self,
        *,
        result: AccessGroupActionGrantChangeResultDTO,
        before_revision: int,
        before_can_grant: bool | None,
    ) -> None:
        """Save the immutable business receipt with the same reservation and transaction."""
        ...
