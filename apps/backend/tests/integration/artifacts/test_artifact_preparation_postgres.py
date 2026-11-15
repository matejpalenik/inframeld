"""Qualify original storage transitions separately from real object-store evidence."""

import asyncio
import os
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from sqlalchemy import select
from tests.support.artifact_scenarios import (
    allocate_artifact,
    artifact_scenario,
    seed_artifact_scope,
)

from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactReservationError
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_staging_reservation_reader import (
    PostgresArtifactStagingReservationReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_attempt_repository import (
    PostgresArtifactAttemptRepository,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.private_artifact_staging import (
    PrivateArtifactStaging,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_target_row import (
    ArtifactCleanupTargetRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires maintained disposable PostgreSQL.",
)


@pytest.mark.asyncio
async def test_original_intent_is_single_use_and_verification_publication_keep_remote_uncertainty(
    database: Database,
) -> None:
    scope = await seed_artifact_scope(database)
    allocation = await allocate_artifact(database, artifact_scenario(scope))
    original = allocation.reservation
    attempt = ArtifactAttemptDTO(
        original.artifact_id,
        original.attempt_id,
        scope,
        3,
        ArtifactContentDigest.from_content(b"abc"),
    )
    async with database.session() as session:
        repository = PostgresArtifactAttemptRepository(session)
        async with session.begin():
            await repository.seal(allocation, attempt)
        async with session.begin():
            assert await repository.begin_put(allocation, attempt)
        async with session.begin():
            assert not await repository.begin_put(allocation, attempt)
        with pytest.raises(ArtifactReservationError):
            async with session.begin():
                await repository.publish_verified(allocation, VerifiedArtifactDTO(attempt))
        async with session.begin():
            # Supplied readback evidence tests SQL transitions only, not S3 verification.
            await repository.confirm_verified(allocation, VerifiedArtifactDTO(attempt))
            await repository.publish_verified(allocation, VerifiedArtifactDTO(attempt))
    facts = await PostgresArtifactStagingReservationReader(database).read(original.reservation_id)
    assert facts is not None and facts.published and facts.put_confirmed and facts.put_pending
    assert not facts.released and not facts.retired
    async with database.session() as session:
        reservation = await session.get(
            ArtifactStagingReservationRow, original.reservation_id.value
        )
        obligation = await session.get(
            ArtifactCleanupObligationRow, allocation.cleanup_binding.obligation_id.value
        )
        assert reservation is not None and reservation.remote_reserved_bytes == original.limit_bytes
        assert obligation is not None and not obligation.physically_complete


@pytest.mark.asyncio
async def test_retirement_and_target_changes_prevent_seal_without_partial_mutation(
    database: Database,
) -> None:
    scope = await seed_artifact_scope(database)
    allocation = await allocate_artifact(database, artifact_scenario(scope), transfer_seconds=10)
    original = allocation.reservation
    target = ArtifactCleanupTargetDTO(original.artifact_id, original.attempt_id, scope, None, None)
    await _wait_for_original_deadline(database, allocation)
    async with database.session() as session:
        repository = PostgresArtifactAttemptRepository(session)
        async with session.begin():
            assert await repository.retire_local(allocation.cleanup_binding, target)
        attempt = ArtifactAttemptDTO(
            original.artifact_id,
            original.attempt_id,
            scope,
            3,
            ArtifactContentDigest.from_content(b"abc"),
        )
        with pytest.raises(ArtifactReservationError):
            async with session.begin():
                await repository.seal(allocation, attempt)
        async with session.begin():
            row = await session.scalar(
                select(ArtifactAttemptRow).where(ArtifactAttemptRow.id == original.attempt_id.value)
            )
            assert row is not None and row.retired and row.length is None and row.digest is None
        with pytest.raises(ArtifactReservationError):
            async with session.begin():
                await repository.confirm_local_removed(
                    allocation.cleanup_binding, replace(target, length=3, digest=attempt.digest)
                )


@dataclass(frozen=True, slots=True)
class _SettlementState:
    ledger: tuple[int, int, int]
    reservation: tuple[int, int, bool, bool]
    attempt: tuple[bool, bool, bool, bool, bool, int | None, bytes | None]
    target: tuple[bool, bool]
    physically_complete: bool


async def _settlement_state(
    database: Database, allocation: ArtifactAllocationDTO
) -> _SettlementState:
    original = allocation.reservation
    async with database.session() as session:
        ledger = await session.get(ArtifactStorageCapacityRow, original.scope.installation_id.value)
        reservation = await session.get(
            ArtifactStagingReservationRow, original.reservation_id.value
        )
        attempt = await session.get(ArtifactAttemptRow, original.attempt_id.value)
        target = await session.get(
            ArtifactCleanupTargetRow,
            (allocation.cleanup_binding.obligation_id.value, original.attempt_id.value),
        )
        obligation = await session.get(
            ArtifactCleanupObligationRow, allocation.cleanup_binding.obligation_id.value
        )
        assert (
            ledger is not None
            and reservation is not None
            and attempt is not None
            and target is not None
            and obligation is not None
        )
        return _SettlementState(
            (ledger.spool_reserved_bytes, ledger.protected_reserved_bytes, ledger.occupied_bytes),
            (
                reservation.local_reserved_bytes,
                reservation.remote_reserved_bytes,
                reservation.released,
                reservation.staging_removed,
            ),
            (
                attempt.retired,
                attempt.published,
                attempt.put_pending,
                attempt.put_confirmed,
                attempt.remote_removed,
                attempt.length,
                attempt.digest,
            ),
            (target.staging_confirmed_removed, target.remote_confirmed_removed),
            obligation.physically_complete,
        )


async def _wait_for_original_deadline(
    database: Database, allocation: ArtifactAllocationDTO
) -> None:
    """Wait for the unchanged saved deadline after successful allocation admission."""
    original = allocation.reservation
    reader = PostgresArtifactStagingReservationReader(database)
    before = await reader.read(original.reservation_id)
    assert before is not None and before.expires_at == original.expires_at
    remaining = (before.expires_at - before.observed_at).total_seconds()
    assert remaining <= 10
    await asyncio.sleep(max(0, remaining) + 0.01)
    after = await reader.read(original.reservation_id)
    assert after is not None and after.expires_at == original.expires_at
    assert after.observed_at >= original.expires_at


async def _remove_allocated_local_target(
    database: Database, allocation: ArtifactAllocationDTO, root: Path, *, pending: bool
) -> ArtifactCleanupTargetDTO:
    original = allocation.reservation
    length = 3 if pending else None
    digest = ArtifactContentDigest.from_content(b"abc") if pending else None
    if pending:
        # A supplied sealed, unknown-write row exercises SQL accounting only.
        # It is not evidence of an executed object-store call or its exclusion.
        async with database.session() as session, session.begin():
            row = await session.get(ArtifactAttemptRow, original.attempt_id.value)
            assert row is not None
            row.length, row.digest, row.put_pending, row.state = (
                length,
                digest.value if digest is not None else None,
                True,
                "put_pending",
            )
    target = ArtifactCleanupTargetDTO(
        original.artifact_id, original.attempt_id, original.scope, length, digest
    )
    await _wait_for_original_deadline(database, allocation)
    async with database.session() as session, session.begin():
        assert await PostgresArtifactAttemptRepository(session).retire_local(
            allocation.cleanup_binding, target
        )
    # This exact allocation has no local file. Exercise real locking and durable
    # parent absence rather than treating expiry as removal evidence.
    await asyncio.to_thread(root.mkdir, mode=0o700)
    staging = PrivateArtifactStaging(root, PostgresArtifactStagingReservationReader(database))
    await staging.startup()
    await staging.remove(target)
    return target


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pending", [False, True], ids=["unsealed_never_started", "sealed_unknown_put"]
)
async def test_local_release_preserves_other_occupied_bytes_and_remote_evidence_on_reconfirmation(
    database: Database, tmp_path: Path, pending: bool
) -> None:
    scope = await seed_artifact_scope(database)
    allocation = await allocate_artifact(database, artifact_scenario(scope), transfer_seconds=10)
    original = allocation.reservation
    unrelated = 100 * 1024**2
    async with database.session() as session, session.begin():
        ledger = await session.get(ArtifactStorageCapacityRow, scope.installation_id.value)
        assert ledger is not None
        ledger.protected_reserved_bytes += unrelated
        ledger.occupied_bytes = unrelated
    target = await _remove_allocated_local_target(
        database, allocation, tmp_path / "staging", pending=pending
    )
    before = await _settlement_state(database, allocation)
    assert before.ledger == (original.limit_bytes, 2 * original.limit_bytes + unrelated, unrelated)
    for _ in range(2):
        async with database.session() as session, session.begin():
            await PostgresArtifactAttemptRepository(session).confirm_local_removed(
                allocation.cleanup_binding, target
            )
        after = await _settlement_state(database, allocation)
        assert after.ledger == (0, original.limit_bytes + unrelated, unrelated)
        assert after.reservation == (0, original.limit_bytes, True, True)
        assert after.attempt == before.attempt
        assert after.target == (True, before.target[1])
        assert not after.physically_complete and not before.physically_complete


@pytest.mark.asyncio
async def test_local_release_rejects_inconsistent_remaining_occupancy_without_clamping(
    database: Database, tmp_path: Path
) -> None:
    scope = await seed_artifact_scope(database)
    allocation = await allocate_artifact(database, artifact_scenario(scope), transfer_seconds=10)
    target = await _remove_allocated_local_target(
        database, allocation, tmp_path / "staging", pending=False
    )
    async with database.session() as session, session.begin():
        ledger = await session.get(ArtifactStorageCapacityRow, scope.installation_id.value)
        assert ledger is not None
        # The row satisfies its current SQL constraint, but the proposed local
        # release would leave less protected capacity than already occupied.
        ledger.occupied_bytes = 40 * 1024**2
    before = await _settlement_state(database, allocation)
    with pytest.raises(ArtifactReservationError):
        async with database.session() as session, session.begin():
            await PostgresArtifactAttemptRepository(session).confirm_local_removed(
                allocation.cleanup_binding, target
            )
    assert await _settlement_state(database, allocation) == before
