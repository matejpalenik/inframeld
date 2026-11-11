from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from inframeld_backend.access.application.dtos.application_account_deletion_record_dto import (
    ApplicationAccountDeletionRecordDTO,
)


class ApplicationAccountDeletionWriter(Protocol):
    """Persist retirement, one revision increment, audit and immutable original.

    Use the caller's transaction and original deadline. Retire the exact principal,
    revoke every key including expired keys, preserving prior revoked_at times.
    Remove received grants, manager assignments before group memberships, Project
    membership and administration grants targeting the account. Preserve inert
    identity, credentials, Name, groups, defaults and unrelated Project work.
    Never commit, retry or swallow cancellation. Shared reservation completion
    remains with the service in this same transaction.
    """

    @abstractmethod
    async def save(
        self,
        *,
        original: ApplicationAccountDeletionRecordDTO,
        expected_project_revision: int,
        checked_at: datetime,
    ) -> None: ...
