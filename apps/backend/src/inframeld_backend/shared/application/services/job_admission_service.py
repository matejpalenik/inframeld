from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.action_authorizer import ActionAuthorizer
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    InvalidInputError,
)
from inframeld_backend.shared.application.errors.job_errors import UnsupportedJobPayloadError
from inframeld_backend.shared.application.protocols.job_admission_audit_writer import (
    JobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
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
        evidence = access.authentication_evidence
        if isinstance(evidence, BrowserSessionAuthenticationDTO):
            raise InvalidInputError(
                "Browser durable admission requires a qualified generation capture."
            )
        if isinstance(evidence, HumanOAuthCredentialBindingDTO):
            if (
                authority.principal_kind is not PrincipalKind.HUMAN
                or authority.human_binding != evidence
            ):
                raise InvalidInputError(
                    "Human admission must preserve its verified OAuth generation."
                )
        elif (
            authority.principal_kind is not PrincipalKind.APPLICATION
            or authority.human_binding is not None
        ):
            raise InvalidInputError("Application admission has incompatible authority evidence.")
        if access.actor_principal_id != authority.principal_id:
            raise RuntimeError("Admission authority belongs to another authenticated principal.")
        authorization = await self._authorizer.require_authorization(
            access=access,
            request=ProjectActionAuthorizationRequestDTO(authority.project_id, authority.action_id),
        )
        if (
            authorization.organization_id != authority.organization_id
            or authorization.project_id != authority.project_id
        ):
            raise RuntimeError("Admission authorization returned another scope.")
        await self._work_authorizer.require_current(authority)
        operation = await self._idempotency.find_or_reserve(
            context=context,
            access=access,
            authorization=authorization,
            fingerprint=fingerprint,
            expected_replay_kind=OperationReplayKind.ASYNC_JOB,
            lookup_authority=OperationLookupAuthority(
                OperationLookupAuthorityFamily.PROJECT_ACTION_USE, authority.action_id
            ),
        )
        if isinstance(operation, AcceptedAsyncOperationDTO):
            saved = await self._jobs.find(operation.operation_id)
            if saved is None:
                raise ConflictError("The accepted operation has no authoritative job binding.")
            original = saved.authority
            if (
                original.principal_id != authority.principal_id
                or original.installation_id != authority.installation_id
                or original.organization_id != authority.organization_id
                or original.project_id != authority.project_id
                or original.action_id != authority.action_id
                or saved.payload != payload
            ):
                raise ConflictError("The retry does not match the original admitted work.")
            return JobAdmissionDTO(saved.job_id, saved.operation_id, False)
        if not isinstance(operation, NewOperationReservationDTO):
            raise ConflictError("The original operation cannot admit new background work.")
        if (payload.kind, payload.version) not in self._supported_payloads:
            raise UnsupportedJobPayloadError("This release does not support the job payload.")
        admission = await self._jobs.admit(
            operation_id=operation.operation_id,
            request_id=request_id,
            authority=authority,
            payload=payload,
            capacity=self._capacity,
        )
        await self._audit.append(
            admission, request_id=request_id, authority=authority, payload=payload
        )
        accepted = await self._idempotency.record_completed_result(
            operation, replay_kind=OperationReplayKind.ASYNC_JOB
        )
        if not isinstance(accepted, AcceptedAsyncOperationDTO):
            raise ConflictError("The new job has no asynchronous admission outcome.")
        return admission
