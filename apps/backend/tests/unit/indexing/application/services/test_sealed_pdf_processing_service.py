import asyncio
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import BinaryIO, cast, override
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.parsed_pdf_dto import ParsedPdfDTO
from inframeld_backend.indexing.application.errors.pdf_parse_error import PdfParseError
from inframeld_backend.indexing.application.protocols.pdf_parser import PdfParser
from inframeld_backend.indexing.application.services.sealed_pdf_processing_service import (
    SealedPdfProcessingService,
)
from inframeld_backend.indexing.domain.value_objects.docling_processing_definition import (
    DoclingProcessingDefinition,
)
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_listing_dto import ArtifactListingDTO
from inframeld_backend.shared.application.dtos.artifact_object_dto import ArtifactObjectDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactStoreUnavailableError,
)
from inframeld_backend.shared.application.protocols.artifact_store import ArtifactStore
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.job_effect_id import JobEffectId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

_SOURCE = b"%PDF-1.7\ncontrolled-source\n"
_SEAL = ArtifactAttemptDTO(
    ArtifactId(UUID(int=4)),
    ArtifactAttemptId(UUID(int=5)),
    ArtifactScopeDTO(
        InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
    ),
    len(_SOURCE),
    ArtifactContentDigest.from_content(_SOURCE),
)
_ATTEMPT_ID = UUID(int=6)
_DEFINITION = DoclingProcessingDefinition(
    docling_slim_version="2.148.0",
    docling_core_version="2.106.0",
    asset_manifest_sha256="7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
    max_content_tokens=8,
    merge_peers=False,
    repeat_table_header=True,
    ocr_enabled=False,
)
_RESULT = ParsedPdfDTO(
    attempt_id=_ATTEMPT_ID,
    source_digest=_SEAL.digest,
    canonical_digest=ArtifactContentDigest.from_content(b"checked output"),
    canonical_bytes=b"checked output",
    chunk_ranges=((0, 1),),
)


class _ReadOnlyStore(ArtifactStore):
    def __init__(
        self, chunks: tuple[bytes, ...], *, wait: bool = False, unavailable: bool = False
    ) -> None:
        self.chunks = chunks
        self.wait = wait
        self.unavailable = unavailable
        self.reads: list[ArtifactAttemptDTO] = []
        self.read_started = asyncio.Event()
        self.closed = False

    @override
    async def read(self, attempt: ArtifactAttemptDTO) -> AsyncGenerator[bytes]:
        self.reads.append(attempt)
        self.read_started.set()
        try:
            for chunk in self.chunks:
                yield chunk
            if self.wait:
                await asyncio.Event().wait()
            if self.unavailable:
                raise ArtifactStoreUnavailableError("controlled private endpoint")
        finally:
            self.closed = True

    @override
    async def put(
        self,
        attempt: ArtifactAttemptDTO,
        content: BinaryIO,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        raise AssertionError("Processing cannot write source storage.")

    @override
    async def head(
        self, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactObjectDTO | None:
        raise AssertionError("Metadata cannot replace full source readback.")

    @override
    async def list(
        self, scope: ArtifactScopeDTO, *, after: ArtifactAttemptId | None, limit: int
    ) -> ArtifactListingDTO:
        raise AssertionError("Processing only reads the exact sealed attempt.")

    @override
    async def delete(
        self,
        scope: ArtifactScopeDTO,
        attempt_id: ArtifactAttemptId,
        *,
        observation: JobEffectId | None = None,
    ) -> None:
        raise AssertionError("Processing cannot delete source storage.")


class _RecordingParser(PdfParser):
    def __init__(
        self, store: _ReadOnlyStore, *, wait: bool = False, failure: PdfParseError | None = None
    ) -> None:
        self._store = store
        self._wait = wait
        self._failure = failure
        self.calls: list[
            tuple[bytes, UUID, ArtifactContentDigest, DoclingProcessingDefinition, float]
        ] = []

    @override
    async def parse(
        self,
        source: bytes,
        *,
        attempt_id: UUID,
        source_digest: ArtifactContentDigest,
        definition: DoclingProcessingDefinition,
        deadline: float,
    ) -> ParsedPdfDTO:
        assert self._store.closed
        self.calls.append((source, attempt_id, source_digest, definition, deadline))
        if self._wait:
            await asyncio.Event().wait()
        if self._failure is not None:
            raise self._failure
        return _RESULT


@pytest.mark.asyncio
async def test_reads_the_original_seal_and_uses_the_same_deadline_for_the_parser() -> None:
    store = _ReadOnlyStore((_SOURCE[:8], b"", _SOURCE[8:]))
    parser = _RecordingParser(store)
    deadline = asyncio.get_running_loop().time() + 1
    result = await SealedPdfProcessingService(store, parser).process(
        _SEAL, attempt_id=_ATTEMPT_ID, definition=_DEFINITION, deadline=deadline
    )
    assert store.reads == [_SEAL]
    assert parser.calls == [(_SOURCE, _ATTEMPT_ID, _SEAL.digest, _DEFINITION, deadline)]
    assert result is _RESULT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "chunks",
    [
        (_SOURCE[:-1],),
        (_SOURCE, b"extra"),
        (b"x" * len(_SOURCE),),
        (cast("bytes", bytearray(_SOURCE)),),
    ],
)
async def test_closes_a_wrong_source_without_dispatching(chunks: tuple[bytes, ...]) -> None:
    store = _ReadOnlyStore(chunks)
    parser = _RecordingParser(store)
    with pytest.raises(PdfParseError) as failure:
        await SealedPdfProcessingService(store, parser).process(
            _SEAL,
            attempt_id=_ATTEMPT_ID,
            definition=_DEFINITION,
            deadline=asyncio.get_running_loop().time() + 1,
        )
    assert failure.value.cleanup_confirmed
    assert store.reads == [_SEAL] and store.closed
    assert not parser.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("length", [0, True, 25 * 1024**2 + 1])
async def test_invalid_or_oversized_source_seal_never_reaches_storage(length: int) -> None:
    store = _ReadOnlyStore(())
    parser = _RecordingParser(store)
    with pytest.raises(PdfParseError) as failure:
        await SealedPdfProcessingService(store, parser).process(
            replace(_SEAL, length=length),
            attempt_id=_ATTEMPT_ID,
            definition=_DEFINITION,
            deadline=asyncio.get_running_loop().time() + 1,
        )
    assert failure.value.cleanup_confirmed
    assert not store.reads and not parser.calls


@pytest.mark.asyncio
async def test_failed_read_stays_private_and_never_dispatches() -> None:
    store = _ReadOnlyStore((_SOURCE,), unavailable=True)
    parser = _RecordingParser(store)
    with pytest.raises(PdfParseError) as failure:
        await SealedPdfProcessingService(store, parser).process(
            _SEAL,
            attempt_id=_ATTEMPT_ID,
            definition=_DEFINITION,
            deadline=asyncio.get_running_loop().time() + 1,
        )
    assert failure.value.cleanup_confirmed
    assert "private endpoint" not in str(failure.value)
    assert store.closed and not parser.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("during_parser", [False, True])
async def test_one_deadline_bounds_the_read_and_parser_without_claiming_unknown_cleanup(
    during_parser: bool,
) -> None:
    store = _ReadOnlyStore((_SOURCE,), wait=not during_parser)
    parser = _RecordingParser(store, wait=during_parser)
    with pytest.raises(PdfParseError, match="deadline") as failure:
        await SealedPdfProcessingService(store, parser).process(
            _SEAL,
            attempt_id=_ATTEMPT_ID,
            definition=_DEFINITION,
            deadline=asyncio.get_running_loop().time() + 0.025,
        )
    assert failure.value.cleanup_confirmed is not during_parser
    assert bool(parser.calls) is during_parser
    assert store.closed


@pytest.mark.asyncio
async def test_worker_cancellation_closes_the_read_and_propagates() -> None:
    store = _ReadOnlyStore((_SOURCE,), wait=True)
    parser = _RecordingParser(store)
    async with asyncio.timeout(1), asyncio.TaskGroup() as tasks:
        processing = tasks.create_task(
            SealedPdfProcessingService(store, parser).process(
                _SEAL,
                attempt_id=_ATTEMPT_ID,
                definition=_DEFINITION,
                deadline=asyncio.get_running_loop().time() + 1,
            )
        )
        await store.read_started.wait()
        processing.cancel()
        with pytest.raises(asyncio.CancelledError):
            await processing
    assert store.closed
    assert not parser.calls


@pytest.mark.asyncio
async def test_parser_failure_preserves_its_cleanup_state() -> None:
    store = _ReadOnlyStore((_SOURCE,))
    original = PdfParseError("The parser cleanup could not be confirmed.")
    parser = _RecordingParser(store, failure=original)
    with pytest.raises(PdfParseError) as failure:
        await SealedPdfProcessingService(store, parser).process(
            _SEAL,
            attempt_id=_ATTEMPT_ID,
            definition=_DEFINITION,
            deadline=asyncio.get_running_loop().time() + 1,
        )
    assert failure.value is original
