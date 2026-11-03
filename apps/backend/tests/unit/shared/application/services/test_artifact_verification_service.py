import hashlib
from collections.abc import AsyncGenerator
from dataclasses import replace
from typing import BinaryIO, override
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_listing_dto import ArtifactListingDTO
from inframeld_backend.shared.application.dtos.artifact_object_dto import ArtifactObjectDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactIntegrityError,
    ArtifactStoreUnavailableError,
)
from inframeld_backend.shared.application.protocols.artifact_store import ArtifactStore
from inframeld_backend.shared.application.services.artifact_verification_service import (
    ArtifactVerificationService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

SCOPE = ArtifactScopeDTO(
    InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
)
ATTEMPT = ArtifactAttemptDTO(
    ArtifactId(UUID(int=4)),
    ArtifactAttemptId(UUID(int=5)),
    SCOPE,
    3,
    ArtifactContentDigest(hashlib.sha256(b"abc").digest()),
)


class MockReadbackStore(ArtifactStore):
    def __init__(self, chunks: tuple[bytes, ...], *, fail_after: bool = False) -> None:
        self.chunks = chunks
        self.fail_after = fail_after
        self.started = False
        self.closed = False

    @override
    async def read(self, attempt: ArtifactAttemptDTO) -> AsyncGenerator[bytes]:
        assert attempt == ATTEMPT
        self.started = True
        try:
            for chunk in self.chunks:
                yield chunk
            if self.fail_after:
                raise ArtifactStoreUnavailableError("Readback unavailable.")
        finally:
            self.closed = True

    @override
    async def put(self, attempt: ArtifactAttemptDTO, content: BinaryIO) -> None:
        raise AssertionError("Verification cannot dispatch another upload.")

    @override
    async def head(
        self, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactObjectDTO | None:
        raise AssertionError("Metadata cannot replace complete readback.")

    @override
    async def list(
        self, scope: ArtifactScopeDTO, *, after: ArtifactAttemptId | None, limit: int
    ) -> ArtifactListingDTO:
        raise AssertionError("Verification reads only the original attempt.")

    @override
    async def delete(self, scope: ArtifactScopeDTO, attempt_id: ArtifactAttemptId) -> None:
        raise AssertionError("Verification cannot delete storage evidence.")


@pytest.mark.asyncio
async def test_verifies_complete_stream_and_preserves_original_attempt() -> None:
    store = MockReadbackStore((b"a", b"", b"bc"))
    result = await ArtifactVerificationService(store).verify(ATTEMPT)
    assert result.attempt == ATTEMPT and store.closed


@pytest.mark.asyncio
@pytest.mark.parametrize("chunks", [(b"ab",), (b"abc", b"d"), (b"xyz",)])
async def test_partial_oversized_or_mismatched_content_never_verifies(
    chunks: tuple[bytes, ...],
) -> None:
    store = MockReadbackStore(chunks)
    with pytest.raises(ArtifactIntegrityError):
        await ArtifactVerificationService(store).verify(ATTEMPT)
    assert store.closed


@pytest.mark.asyncio
async def test_unavailable_readback_never_establishes_absence_or_reuploads() -> None:
    store = MockReadbackStore((b"ab",), fail_after=True)
    with pytest.raises(ArtifactStoreUnavailableError):
        await ArtifactVerificationService(store).verify(ATTEMPT)
    assert store.closed


@pytest.mark.asyncio
async def test_excessive_expectation_is_rejected_before_storage_access() -> None:
    store = MockReadbackStore(())
    with pytest.raises(ArtifactCapacityError):
        await ArtifactVerificationService(store, max_bytes=2).verify(ATTEMPT)
    assert not store.started


@pytest.mark.asyncio
async def test_invalid_sealed_length_is_rejected_before_storage_access() -> None:
    store = MockReadbackStore(())
    with pytest.raises(ArtifactIntegrityError):
        await ArtifactVerificationService(store).verify(replace(ATTEMPT, length=-1))
    assert not store.started
