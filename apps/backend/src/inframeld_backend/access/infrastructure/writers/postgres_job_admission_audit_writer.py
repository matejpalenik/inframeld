from typing import override
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
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
        if not self._session.in_transaction() or not admission.created:
            raise RuntimeError("Audit only a new job in its original admission transaction.")
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=authority.organization_id.value,
                project_id=authority.project_id.value,
                actor_kind=authority.principal_kind.value,
                actor_principal_id=authority.principal_id.value,
                event_type="job_admitted",
                target_kind="job",
                target_id=admission.job_id.value,
                action=authority.action_id.value,
                correlation_id=admission.operation_id.value,
                after_values={
                    "request_id": str(request_id.value),
                    "payload_kind": payload.kind,
                    "payload_version": payload.version,
                },
            )
        )
        await self._session.flush()
