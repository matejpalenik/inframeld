from abc import abstractmethod
from datetime import datetime
from typing import Protocol
from uuid import UUID

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.enums.job_status import JobStatus
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class JobStore(Protocol):
    """Persist ordinary job mechanics in the caller-owned short transaction.

    Admission shares the authorization, business effects, required audit and
    idempotency transaction. Every authoritative attempt save must match its
    original job and live fence. This capability grants no product authority.
    """

    @abstractmethod
    async def admit(
        self,
        *,
        operation_id: OperationId,
        request_id: RequestId,
        authority: AdmittedWorkAuthorityDTO,
        payload: JobPayload,
        capacity: int,
    ) -> JobAdmissionDTO: ...

    @abstractmethod
    async def find(self, operation_id: OperationId) -> JobSnapshotDTO | None: ...

    @abstractmethod
    async def next_candidate(self) -> JobSnapshotDTO | None: ...

    @abstractmethod
    async def start_attempt(
        self, job: JobSnapshotDTO, *, worker_id: UUID, lease_seconds: float, work_seconds: float
    ) -> JobAttemptContextDTO: ...

    @abstractmethod
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO: ...

    @abstractmethod
    async def checkpoint(
        self, context: JobAttemptContextDTO, data: bytes, *, lease_seconds: float
    ) -> None: ...

    @abstractmethod
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None: ...

    @abstractmethod
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None: ...

    @abstractmethod
    async def finish(
        self, context: JobAttemptContextDTO, *, status: JobStatus, reason: str | None
    ) -> None: ...

    @abstractmethod
    async def retire_attempt(
        self, job: JobSnapshotDTO, *, status: JobStatus, reason: str, due_at: datetime
    ) -> None: ...

    @abstractmethod
    async def request_cancel(self, job_id: JobId) -> None: ...
