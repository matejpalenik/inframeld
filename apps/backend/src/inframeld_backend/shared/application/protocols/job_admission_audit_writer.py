from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class JobAdmissionAuditWriter(Protocol):
    """Append required attribution in the same caller transaction as job admission."""

    @abstractmethod
    async def append(
        self,
        admission: JobAdmissionDTO,
        *,
        request_id: RequestId,
        authority: AdmittedWorkAuthorityDTO,
        payload: JobPayload,
    ) -> None: ...
