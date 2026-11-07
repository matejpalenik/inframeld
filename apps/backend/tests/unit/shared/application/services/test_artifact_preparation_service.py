from collections.abc import AsyncGenerator, AsyncIterable
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID

import pytest

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.protocols.artifact_preparation_io import (
    ArtifactPreparationIO,
)
from inframeld_backend.shared.application.protocols.artifact_preparation_records import (
    ArtifactPreparationRecords,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.artifact_preparation_service import (
    ArtifactPreparationService,
)
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
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

NOW = datetime.now(UTC)
SCOPE = ArtifactScopeDTO(
    InstallationId(UUID(int=1)), OrganizationId(UUID(int=2)), ProjectId(UUID(int=3))
)
RESERVATION = ArtifactStagingReservationDTO(
    ArtifactStagingReservationId(UUID(int=4)),
    ArtifactId(UUID(int=5)),
    ArtifactAttemptId(UUID(int=6)),
    SCOPE,
    25 * 1024**2,
    NOW + timedelta(hours=1),
    NOW,
)
BINDING = ArtifactCleanupJobBindingDTO(
    ArtifactCleanupObligationId(UUID(int=7)),
    SCOPE,
    ArtifactCleanupKind.ABANDONED_STAGING,
    UnadmittedStagingArtifactOriginDTO(RESERVATION.attempt_id, RequestId(UUID(int=8))),
)
ALLOCATION = ArtifactAllocationDTO(RESERVATION, BINDING, JobId(UUID(int=9)))
SEALED = ArtifactAttemptDTO(
    RESERVATION.artifact_id,
    RESERVATION.attempt_id,
    SCOPE,
    3,
    ArtifactContentDigest.from_content(b"abc"),
)


class MockTransactions(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.active = False
        self.events = events

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        assert not self.active
        self.active = True
        try:
            yield
        finally:
            self.active = False
            self.events.append("sql_closed")


class MockAttempts(ArtifactPreparationRecords):
    def __init__(self, events: list[str], transactions: MockTransactions) -> None:
        self.events = events
        self._transactions = transactions
        self.facts = RESERVATION

    @override
    async def inspect(self, allocation: ArtifactAllocationDTO) -> ArtifactStagingReservationDTO:
        async with self._transactions.begin():
            assert allocation == ALLOCATION
            return self.facts

    @override
    async def seal(self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO) -> None:
        async with self._transactions.begin():
            self.events.append("seal")
            self.facts = replace(self.facts, length=attempt.length, digest=attempt.digest)

    @override
    async def begin_put(
        self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO
    ) -> bool:
        async with self._transactions.begin():
            self.events.append("put_intent")
            first = not self.facts.put_pending
            self.facts = replace(self.facts, put_pending=True)
            return first

    @override
    async def confirm_verified(
        self, allocation: ArtifactAllocationDTO, verified: VerifiedArtifactDTO
    ) -> None:
        async with self._transactions.begin():
            assert verified.attempt == SEALED
            self.events.append("verified")
            self.facts = replace(self.facts, put_confirmed=True)


class MockContent(ArtifactPreparationIO):
    def __init__(self, transactions: MockTransactions, events: list[str]) -> None:
        self._transactions, self.events = transactions, events
        self.failure: Exception | None = None

    @override
    @asynccontextmanager
    async def hold(self, allocation: ArtifactAllocationDTO) -> AsyncGenerator[None]:
        self.events.append("locked")
        try:
            yield
        finally:
            self.events.append("drained_unlocked")

    @override
    async def stage(
        self, allocation: ArtifactAllocationDTO, chunks: AsyncIterable[bytes]
    ) -> ArtifactAttemptDTO:
        assert not self._transactions.active
        assert b"".join([part async for part in chunks]) == b"abc"
        self.events.append("stage")
        return SEALED

    @override
    async def verify(self, attempt: ArtifactAttemptDTO, *, upload: bool) -> VerifiedArtifactDTO:
        assert not self._transactions.active
        self.events.append("put" if upload else "readback_only")
        if self.failure:
            raise self.failure
        return VerifiedArtifactDTO(attempt)


async def _chunks() -> AsyncGenerator[bytes]:
    yield b"abc"


def _service() -> tuple[ArtifactPreparationService, MockAttempts, MockContent, list[str]]:
    events: list[str] = []
    transactions = MockTransactions(events)
    attempts = MockAttempts(events, transactions)
    content = MockContent(transactions, events)
    return ArtifactPreparationService(attempts, content), attempts, content, events


@pytest.mark.asyncio
async def test_seal_and_put_intent_commit_before_io_and_verification_preserves_uncertainty() -> (
    None
):
    service, attempts, _, events = _service()
    assert await service.prepare(ALLOCATION, _chunks()) == VerifiedArtifactDTO(SEALED)
    assert events == [
        "locked",
        "sql_closed",
        "stage",
        "seal",
        "sql_closed",
        "put_intent",
        "sql_closed",
        "put",
        "verified",
        "sql_closed",
        "drained_unlocked",
    ]
    assert attempts.facts.put_confirmed and attempts.facts.put_pending
    assert not attempts.facts.released and not attempts.facts.published


@pytest.mark.asyncio
async def test_lost_response_resumes_the_original_key_without_another_put() -> None:
    service, attempts, content, events = _service()
    content.failure = ArtifactWriteOutcomeUnknownError("Lost original response.")
    with pytest.raises(ArtifactWriteOutcomeUnknownError):
        await service.prepare(ALLOCATION, _chunks())
    assert attempts.facts.put_pending and not attempts.facts.put_confirmed
    content.failure = None
    assert await service.resume(ALLOCATION) == VerifiedArtifactDTO(SEALED)
    assert events.count("put") == 1 and events.count("readback_only") == 1
    assert attempts.facts.put_pending and attempts.facts.put_confirmed


@pytest.mark.asyncio
async def test_unavailable_original_readback_never_repeats_the_pending_put() -> None:
    service, attempts, content, events = _service()
    content.failure = ArtifactWriteOutcomeUnknownError("The original object remains unavailable.")
    with pytest.raises(ArtifactWriteOutcomeUnknownError):
        await service.prepare(ALLOCATION, _chunks())
    with pytest.raises(ArtifactWriteOutcomeUnknownError):
        await service.resume(ALLOCATION)
    assert events.count("put") == events.count("readback_only") == 1
    assert attempts.facts.put_pending and not attempts.facts.put_confirmed
