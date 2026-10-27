from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class IdentityRecoveryCleanupFactsReader(Protocol):
    """Read execution observations within the caller's bounded transaction.

    Select a candidate without locks, then acquire identity coordination before
    locking and rereading its job and run. A candidate is not dispatch authority.
    """

    @abstractmethod
    async def next_candidate(self) -> OperationId | None: ...

    @abstractmethod
    async def lock_work(
        self, operation_id: OperationId
    ) -> IdentityRecoveryCleanupWorkDTO | None: ...
