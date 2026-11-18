from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.pipelines.application.protocols.pipeline_pdf_preparation_facts_reader import (
    PipelinePdfPreparationFactsReader,
)
from inframeld_backend.pipelines.application.value_objects.pipeline_pdf_preparation_input import (
    PipelinePdfPreparationInput,
)
from inframeld_backend.pipelines.domain.enums.pipeline_action import PipelineAction
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
)
from inframeld_backend.shared.application.protocols.build_history_reservation_writer import (
    BuildHistoryReservationWriter,
)
from inframeld_backend.shared.application.protocols.job_admission_audit_writer import (
    JobAdmissionAuditWriter,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class PipelinePdfPreparationAdmissionService:
    """Admit the canonical PDF preparation stage of a reviewed private Build.

    Reserve mandatory history, capture fixed inputs and commit job and audit
    together. Replay checks current Build authority before recovering work.
    """

    def __init__(
        self,
        *,
        transactions: TransactionManager,
        facts: PipelinePdfPreparationFactsReader,
        authority: AdmittedWorkAuthorizer,
        idempotency: OperationIdempotency,
        fingerprints: RequestFingerprintService,
        history: BuildHistoryReservationWriter,
        jobs: JobStore,
        audit: JobAdmissionAuditWriter,
    ) -> None:
        self._transactions = transactions
        self._facts = facts
        self._authority = authority
        self._idempotency = idempotency
        self._fingerprints = fingerprints
        self._history = history
        self._jobs = jobs
        self._audit = audit

    async def admit(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        pipeline_id: PipelineId,
        configuration_revision: int,
        collection_revision_id: CollectionRevisionId,
        key: IdempotencyKey,
        request_id: RequestId,
    ) -> JobAdmissionDTO:
        evidence = access.authentication_evidence
        if not isinstance(evidence, HumanOAuthCredentialBindingDTO):
            raise InvalidInputError(
                "PDF preparation requires a verified OAuth credential generation."
            )
        if type(configuration_revision) is not int or not (
            1 <= configuration_revision <= RevisionValidation.MAX_VALUE
        ):
            raise InvalidInputError("A reviewed configuration revision must be positive and exact.")

        fingerprint = self._fingerprints.fingerprint(
            purpose="pipeline-pdf-preparation",
            canonical_request=(
                configuration_revision.to_bytes(8, "big") + collection_revision_id.value.bytes
            ),
        )
        async with self._transactions.begin():
            scope = await self._facts.authorize(
                access=access, project_id=project_id, pipeline_id=pipeline_id
            )
            if scope.project_id != project_id or scope.installation_id != evidence.installation_id:
                raise AccessDeniedError()
            authority = AdmittedWorkAuthorityDTO(
                principal_id=access.actor_principal_id,
                principal_kind=PrincipalKind.HUMAN,
                installation_id=scope.installation_id,
                organization_id=scope.organization_id,
                project_id=project_id,
                action_id=ActionId(PipelineAction.BUILD.value),
                human_binding=evidence,
                pipeline_id=pipeline_id,
            )
            await self._authority.require_current(authority)
            operation = await self._idempotency.reserve_or_recover(
                context=IdempotencyContextDTO(
                    method=HttpMethod.POST,
                    requested_route=f"/internal/projects/{project_id.value}/pipelines/{pipeline_id.value}/builds",
                    key=key,
                ),
                access=access,
                authorization=authority,
                fingerprint=fingerprint,
                expected_replay_kind=OperationReplayKind.ASYNC_JOB,
            )
            if isinstance(operation, AcceptedAsyncOperationDTO):
                return await self._replay(
                    operation, authority, configuration_revision, collection_revision_id
                )
            if not isinstance(operation, NewOperationReservationDTO):
                raise ConflictError("The original Build requires recovery.")

            reviewed = await self._facts.read_reviewed(
                access=access,
                scope=scope,
                pipeline_id=pipeline_id,
                configuration_revision=configuration_revision,
                collection_revision_id=collection_revision_id,
            )
            if (
                reviewed.configuration_revision != configuration_revision
                or reviewed.collection_revision_id != collection_revision_id
            ):
                raise ConflictError("The captured inputs differ from the reviewed Build.")
            payload = reviewed.to_payload()
            await self._history.reserve_build(
                scope=scope, operation_id=operation.operation_id, pipeline_id=pipeline_id
            )
            admission = await self._jobs.admit(
                operation_id=operation.operation_id,
                request_id=request_id,
                authority=authority,
                payload=payload,
                capacity=8,
            )
            await self._audit.append(
                admission, request_id=request_id, authority=authority, payload=payload
            )
            await self._idempotency.record_completed_result(
                operation, replay_kind=OperationReplayKind.ASYNC_JOB
            )
            return admission

    async def _replay(
        self,
        original: AcceptedAsyncOperationDTO,
        current: AdmittedWorkAuthorityDTO,
        configuration_revision: int,
        collection_revision_id: CollectionRevisionId,
    ) -> JobAdmissionDTO:
        saved = await self._jobs.find(original.operation_id)
        if saved is None or not isinstance(saved.binding, ProductJobBindingDTO):
            raise ConflictError("The original Build has no authoritative job binding.")
        prior = saved.binding.authority
        if (
            saved.binding.operation_id != original.operation_id
            or prior.installation_id != current.installation_id
            or prior.organization_id != current.organization_id
            or prior.project_id != current.project_id
            or prior.principal_id != current.principal_id
            or prior.principal_kind != current.principal_kind
            or prior.pipeline_id != current.pipeline_id
            or prior.action_id != current.action_id
        ):
            raise ConflictError("The original Build authority does not match.")
        captured = PipelinePdfPreparationInput.from_payload(saved.payload)
        if (
            captured.configuration_revision != configuration_revision
            or captured.collection_revision_id != collection_revision_id
        ):
            raise ConflictError("The original Build inputs do not match.")
        return JobAdmissionDTO(saved.job_id, original.operation_id, False)
