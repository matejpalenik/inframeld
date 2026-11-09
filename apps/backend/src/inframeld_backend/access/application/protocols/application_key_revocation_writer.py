from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.application_key_revocation_record_dto import (
    ApplicationKeyRevocationRecordDTO,
)


class ApplicationKeyRevocationWriter(Protocol):
    """Save revocation and its safe original without committing or retrying.

    A transition advances one revision and emits one change audit in the caller's
    coordinated transaction. An already-revoked no-op saves only its own original,
    preserving the stored timestamp and revision without a change audit. The
    service completes the shared reservation through OperationIdempotency in the
    same transaction. This writer persists business state and the safe original.
    """

    @abstractmethod
    async def save(
        self, *, original: ApplicationKeyRevocationRecordDTO, expected_project_revision: int
    ) -> None: ...
