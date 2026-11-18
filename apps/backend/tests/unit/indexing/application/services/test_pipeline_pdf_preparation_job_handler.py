from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import create_autospec
from uuid import UUID

import pytest

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_source_id import DocumentSourceId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.parsed_pdf_dto import ParsedPdfDTO
from inframeld_backend.indexing.application.protocols.pipeline_pdf_preparation_records import (
    PipelinePdfPreparationRecords,
)
from inframeld_backend.indexing.application.services.pipeline_pdf_preparation_job_handler import (
    PipelinePdfPreparationJobHandler,
)
from inframeld_backend.indexing.application.services.sealed_pdf_processing_service import (
    SealedPdfProcessingService,
)
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.knowledge.application.value_objects.collection_id import CollectionId
from inframeld_backend.knowledge.application.value_objects.collection_revision_id import (
    CollectionRevisionId,
)
from inframeld_backend.pipelines.application.value_objects.pipeline_pdf_preparation_input import (
    PipelinePdfPreparationInput,
)
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactIntegrityError
from inframeld_backend.shared.application.errors.job_errors import JobFenceLostError
from inframeld_backend.shared.application.protocols.artifact_preparation_io import (
    ArtifactPreparationIO,
)
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

pytestmark = pytest.mark.asyncio

_SCOPE = ArtifactScopeDTO(
    InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
)
_INPUTS = PipelinePdfPreparationInput(
    CollectionId(UUID(int=4)),
    CollectionRevisionId(UUID(int=5)),
    1,
    ProcessingProfileId(UUID(int=6)),
    DocumentSourceId(DocumentId(UUID(int=7)), DocumentVersionId(UUID(int=8))),
)
_BINDING = ProductJobBindingDTO(
    operation_id=OperationId("original-build"),
    request_id=RequestId(UUID(int=9)),
    authority=AdmittedWorkAuthorityDTO(
        principal_id=PrincipalId(UUID(int=10)),
        principal_kind=PrincipalKind.HUMAN,
        installation_id=_SCOPE.installation_id,
        organization_id=_SCOPE.organization_id,
        project_id=_SCOPE.project_id,
        action_id=ActionId("build-pipeline"),
        human_binding=HumanOAuthCredentialBindingDTO(
            VerifiedHumanIdentityDTO(IdentityAuthority("fixture"), IdentitySubject("builder")),
            _SCOPE.installation_id,
            HumanCredentialVersion(1),
        ),
        pipeline_id=PipelineId(UUID(int=11)),
    ),
)
_SOURCE = ArtifactAttemptDTO(
    ArtifactId(UUID(int=12)),
    ArtifactAttemptId(UUID(int=13)),
    _SCOPE,
    4,
    ArtifactContentDigest.from_content(b"%PDF"),
)
_DEFINITION = DoclingProcessingDefinition(
    docling_slim_version="2.148.0",
    docling_core_version="2.106.0",
    asset_manifest_sha256="7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
    max_content_tokens=32,
    merge_peers=False,
    repeat_table_header=True,
    ocr_enabled=False,
)
_FENCE = JobFence(UUID(int=14))
_CANONICAL = (
    '{"format":"inframeld-pdf-canonical-v1","blocks":'
    '[{"kind":"text","pages":[1],"span":[0,7]}],"text":"A🙂B cat"}'
).encode()
_PARSED = ParsedPdfDTO(
    attempt_id=_FENCE.value,
    source_digest=_SOURCE.digest,
    canonical_digest=ArtifactContentDigest.from_content(_CANONICAL),
    canonical_bytes=_CANONICAL,
    chunk_ranges=((0, 3), (4, 7)),
)
_SEALED = ArtifactAttemptDTO(
    ArtifactId(UUID(int=15)),
    ArtifactAttemptId(UUID(int=16)),
    _SCOPE,
    len(_CANONICAL),
    _PARSED.canonical_digest,
)
_OBSERVATION = JobEffectId(UUID(int=17))
_VERIFIED = VerifiedArtifactDTO(_SEALED)


class _Preparation:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.context = JobAttemptContextDTO(
            job_id=JobId(UUID(int=18)),
            binding=_BINDING,
            payload=_INPUTS.to_payload(),
            attempt=1,
            fence=_FENCE,
            work_deadline=now + timedelta(seconds=30),
            checkpoint=b"",
        )
        self.allocation = ArtifactAllocationDTO(
            ArtifactStagingReservationDTO(
                ArtifactStagingReservationId(UUID(int=19)),
                _SEALED.artifact_id,
                _SEALED.attempt_id,
                _SCOPE,
                _SEALED.length,
                now + timedelta(seconds=30),
                now,
            ),
            ArtifactCleanupJobBindingDTO(
                ArtifactCleanupObligationId(UUID(int=20)),
                _SCOPE,
                ArtifactCleanupKind.ABANDONED_STAGING,
                BusinessOperationArtifactOriginDTO(_BINDING.operation_id, _BINDING.request_id),
            ),
            JobId(UUID(int=21)),
        )
        self.records = create_autospec(PipelinePdfPreparationRecords, instance=True)
        self.records.load.return_value = (_SOURCE, _DEFINITION)
        self.records.allocate.return_value = self.allocation
        self.records.begin_put.return_value = _OBSERVATION
        self.records.publish.side_effect = self.publish
        self.processing = create_autospec(SealedPdfProcessingService, instance=True)
        self.processing.process.return_value = _PARSED
        self.io = create_autospec(ArtifactPreparationIO, instance=True)
        self.io.hold.side_effect = self.hold
        self.io.stage.side_effect = self.stage
        self.io.verify.return_value = _VERIFIED
        self.checkpoints = create_autospec(JobCheckpoints, instance=True)
        self.handler = PipelinePdfPreparationJobHandler(
            self.records, self.processing, lambda: self.io
        )
        self.held = False

    @asynccontextmanager
    async def hold(self, allocation: ArtifactAllocationDTO) -> AsyncGenerator[None]:
        assert allocation == self.allocation and not self.held
        self.held = True
        try:
            yield
        finally:
            self.held = False

    async def stage(
        self, allocation: ArtifactAllocationDTO, chunks: AsyncIterable[bytes]
    ) -> ArtifactAttemptDTO:
        assert self.held and allocation == self.allocation
        assert b"".join([chunk async for chunk in chunks]) == _CANONICAL
        return _SEALED

    async def publish(
        self,
        context: JobAttemptContextDTO,
        inputs: PipelinePdfPreparationInput,
        source: ArtifactAttemptDTO,
        allocation: ArtifactAllocationDTO,
        observation: JobEffectId,
        verified: VerifiedArtifactDTO,
        canonical_identity: ArtifactContentDigest,
        chunk_ranges: tuple[tuple[int, int], ...],
    ) -> None:
        assert not self.held
        assert (context, inputs, source) == (self.context, _INPUTS, _SOURCE)
        assert (allocation, observation, verified) == (self.allocation, _OBSERVATION, _VERIFIED)
        assert canonical_identity != _PARSED.canonical_digest
        assert chunk_ranges == _PARSED.chunk_ranges


async def test_verified_original_publishes_ranges_and_completed_replay_has_no_effect() -> None:
    work = _Preparation()
    work.records.load.side_effect = [(_SOURCE, _DEFINITION), None]

    await work.handler.run(work.context, work.checkpoints)
    await work.handler.run(work.context, work.checkpoints)

    work.records.allocate.assert_awaited_once_with(
        work.context, _INPUTS, _SOURCE, len(_CANONICAL), len(_PARSED.chunk_ranges)
    )
    work.records.begin_put.assert_awaited_once_with(
        work.context, _INPUTS, _SOURCE, work.allocation, _SEALED
    )
    work.io.verify.assert_awaited_once_with(_SEALED, upload=True, observation=_OBSERVATION)
    work.records.publish.assert_awaited_once()
    work.processing.process.assert_awaited_once()
    assert work.processing.process.await_args.kwargs["attempt_id"] == work.context.fence.value


async def test_a_lost_fence_after_parse_prevents_any_output_allocation() -> None:
    work = _Preparation()
    work.checkpoints.check.side_effect = [None, JobFenceLostError()]

    with pytest.raises(JobFenceLostError):
        await work.handler.run(work.context, work.checkpoints)

    work.processing.process.assert_awaited_once()
    work.records.allocate.assert_not_awaited()
    work.io.verify.assert_not_awaited()


async def test_another_readback_seal_cannot_publish_or_confirm_progress() -> None:
    work = _Preparation()
    work.io.verify.return_value = VerifiedArtifactDTO(replace(_SEALED, digest=_SOURCE.digest))

    with pytest.raises(ArtifactIntegrityError):
        await work.handler.run(work.context, work.checkpoints)

    work.records.begin_put.assert_awaited_once()
    work.records.publish.assert_not_awaited()
    work.checkpoints.confirm_effect.assert_not_awaited()
