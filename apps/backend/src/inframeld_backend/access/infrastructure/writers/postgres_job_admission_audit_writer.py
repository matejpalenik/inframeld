from typing import override

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.protocols.job_admission_audit_writer import (
    JobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class PostgresJobAdmissionAuditWriter(JobAdmissionAuditWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def append(
        self,
        admission: JobAdmissionDTO,
        *,
        request_id: RequestId,
        authority: AdmittedWorkAuthorityDTO,
        payload: JobPayload,
    ) -> None:
        raise NotImplementedError
