from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.protocols.action_authorizer import ActionAuthorizer
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.protocols.job_admission_audit_writer import (
    JobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId


class JobAdmissionService:
    """Admit or recover original work inside the owning use case's transaction.

    All collaborators share its session. The caller saves business admission in
    that transaction and must not report acceptance before commit succeeds.
    """

    def __init__(
        self,
        authorizer: ActionAuthorizer,
        work_authorizer: AdmittedWorkAuthorizer,
        idempotency: OperationIdempotency,
        jobs: JobStore,
        audit: JobAdmissionAuditWriter,
        *,
        supported_payloads: tuple[tuple[str, int], ...],
        capacity: int = 8,
    ) -> None:
        self._authorizer = authorizer
        self._work_authorizer = work_authorizer
        self._idempotency = idempotency
        self._jobs = jobs
        self._audit = audit
        self._supported_payloads = supported_payloads
        self._capacity = capacity

    async def admit(
        self,
        *,
        access: AccessContextDTO,
        authority: AdmittedWorkAuthorityDTO,
        context: OperationAdmissionContextDTO,
        fingerprint: RequestFingerprint,
        request_id: RequestId,
        payload: JobPayload,
    ) -> JobAdmissionDTO:
        raise NotImplementedError
