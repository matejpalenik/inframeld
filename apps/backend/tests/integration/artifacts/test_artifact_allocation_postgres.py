"""Reserve real byte/obligation/queue records atomically before private storage effects."""

import asyncio
import hashlib
import os
from dataclasses import replace
from datetime import timedelta
from typing import Literal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.artifact_scenarios import (
    ArtifactScenario,
    allocate_artifact,
    artifact_scenario,
    completed_product_origin,
    seed_artifact_scope,
)

from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_capacity_dto import ArtifactCapacityDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactReservationError,
)
from inframeld_backend.shared.application.errors.job_errors import JobQueueFullError
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.resources.database import Database
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
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


async def _allocation_state(
    database: Database, scope: ArtifactScopeDTO
) -> tuple[tuple[int, ...], tuple[int, int, int]]:
    async with database.session() as session:
        counts: list[int] = []
        for model in (
            ArtifactAttemptRow,
            ArtifactStagingReservationRow,
            ArtifactCleanupObligationRow,
            ArtifactCleanupTargetRow,
            DurableJobRow,
            AccessAuditEventRow,
            IdempotencyReservationRow,
        ):
            counts.append((await session.scalar(select(func.count()).select_from(model))) or 0)
        ledger = await session.get(ArtifactStorageCapacityRow, scope.installation_id.value)
        assert ledger is not None
        return tuple(counts), (
            ledger.spool_reserved_bytes,
            ledger.protected_reserved_bytes,
            ledger.occupied_bytes,
        )


async def _assert_allocation_absent(database: Database, scenario: ArtifactScenario) -> None:
    async with database.session() as session:
        assert await session.get(ArtifactAttemptRow, scenario.attempt_id.value) is None
        assert (
            await session.get(ArtifactStagingReservationRow, scenario.reservation_id.value) is None
        )
        assert await session.get(ArtifactCleanupObligationRow, scenario.obligation_id.value) is None
        assert (
            await session.scalar(
                select(DurableJobRow.id).where(
                    DurableJobRow.cleanup_obligation_id == scenario.obligation_id.value
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(ArtifactCleanupTargetRow.attempt_id).where(
                    ArtifactCleanupTargetRow.obligation_id == scenario.obligation_id.value
                )
            )
            is None
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("ceiling", ["spool", "protected"])
async def test_allocation_honors_shared_byte_ceiling_and_rolls_back_overflow(
    database: Database, ceiling: Literal["spool", "protected"]
) -> None:
    scope, origin = await completed_product_origin(database)
    # Controlled persisted totals stand for other retained installation work.
    # They qualify shared-ledger admission, not measured host occupancy.
    spool = 2 * 1024**3 - 1 if ceiling == "spool" else 0
    protected = 2 * spool if ceiling == "spool" else 100 * 1024**3 - 2
    occupied = 0 if ceiling == "spool" else protected
    async with database.session() as session, session.begin():
        session.add(
            ArtifactStorageCapacityRow(
                installation_id=scope.installation_id.value,
                spool_reserved_bytes=spool,
                protected_reserved_bytes=protected,
                occupied_bytes=occupied,
            )
        )

    await allocate_artifact(database, artifact_scenario(scope, origin), limit_bytes=1)
    before = await _allocation_state(database, scope)
    assert before[1] == (spool + 1, protected + 2, occupied)
    assert before[1][0 if ceiling == "spool" else 1] == (
        2 * 1024**3 if ceiling == "spool" else 100 * 1024**3
    )
    rejected = artifact_scenario(scope, origin)
    with pytest.raises(ArtifactCapacityError):
        await allocate_artifact(database, rejected, limit_bytes=1)
    assert await _allocation_state(database, scope) == before
    await _assert_allocation_absent(database, rejected)


@pytest.mark.asyncio
async def test_original_operation_cannot_exceed_frozen_spool_allowance(database: Database) -> None:
    scope, origin = await completed_product_origin(database)
    await allocate_artifact(
        database, artifact_scenario(scope, origin), limit_bytes=256 * 1024**2 - 1
    )
    await allocate_artifact(database, artifact_scenario(scope, origin), limit_bytes=1)
    before = await _allocation_state(database, scope)
    assert before[1] == (256 * 1024**2, 512 * 1024**2, 0)

    rejected = artifact_scenario(scope, origin)
    with pytest.raises(ArtifactCapacityError):
        await allocate_artifact(database, rejected, limit_bytes=1)
    assert await _allocation_state(database, scope) == before
    await _assert_allocation_absent(database, rejected)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("backup_reserved", "floor_free"),
    [(0, 232 * 1024**2 + 4), (30 * 1024**2, 242 * 1024**2 + 2)],
    ids=["projected_backup", "larger_reserved_backup"],
)
@pytest.mark.parametrize("shortfall", [0, 1], ids=["exact_floor", "below_floor"])
async def test_allocation_honors_projected_free_floor(
    database: Database, backup_reserved: int, floor_free: int, shortfall: int
) -> None:
    scope, origin = await completed_product_origin(database)
    # Other work retains 20MiB, with 8MiB occupied. The supplied free-space
    # observation leaves exactly 200/1000MiB after pending growth, this byte's
    # two protected copies and the independent backup allowance are charged.
    async with database.session() as session, session.begin():
        session.add(
            ArtifactStorageCapacityRow(
                installation_id=scope.installation_id.value,
                protected_reserved_bytes=20 * 1024**2,
                occupied_bytes=8 * 1024**2,
            )
        )
    before = await _allocation_state(database, scope)
    scenario = artifact_scenario(scope, origin)
    observation = ArtifactCapacityDTO(1000 * 1024**2, floor_free - shortfall, backup_reserved)
    if shortfall:
        with pytest.raises(ArtifactCapacityError):
            await allocate_artifact(
                database, scenario, limit_bytes=1, physical_capacity=observation
            )
        assert await _allocation_state(database, scope) == before
        await _assert_allocation_absent(database, scenario)
    else:
        await allocate_artifact(database, scenario, limit_bytes=1, physical_capacity=observation)
        after = await _allocation_state(database, scope)
        assert after == (
            tuple(count + 1 for count in before[0][:-1]) + (before[0][-1],),
            (1, 20 * 1024**2 + 2, 8 * 1024**2),
        )


@pytest.mark.asyncio
async def test_distinct_projects_cannot_both_reserve_last_shared_byte(database: Database) -> None:
    first_scope, first_origin = await completed_product_origin(database)
    second_scope, second_origin = await completed_product_origin(database)
    assert first_scope.installation_id == second_scope.installation_id
    assert first_scope.project_id != second_scope.project_id
    assert first_origin.operation_id != second_origin.operation_id
    scenarios = (
        artifact_scenario(first_scope, first_origin),
        artifact_scenario(second_scope, second_origin),
    )
    async with database.session() as session, session.begin():
        session.add(
            ArtifactStorageCapacityRow(
                installation_id=first_scope.installation_id.value,
                spool_reserved_bytes=2 * 1024**3 - 1,
                protected_reserved_bytes=4 * 1024**3 - 2,
            )
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DurableJobRow)
                .where(DurableJobRow.status.in_([JobStatus.QUEUED.value, JobStatus.RUNNING.value]))
            )
            == 0
        )
    before = await _allocation_state(database, first_scope)
    # Distinct Project locks still compete for one installation's last byte.
    # Eight queue slots are available, so a queue rejection cannot mask the race.
    results = await asyncio.gather(
        *(
            allocate_artifact(database, scenario, capacity=8, limit_bytes=1)
            for scenario in scenarios
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ArtifactAllocationDTO) for result in results) == 1
    assert sum(isinstance(result, ArtifactCapacityError) for result in results) == 1
    assert await _allocation_state(database, first_scope) == (
        tuple(count + 1 for count in before[0][:-1]) + (before[0][-1],),
        (2 * 1024**3, 4 * 1024**3, 0),
    )
    for scenario, result in zip(scenarios, results, strict=True):
        if isinstance(result, ArtifactCapacityError):
            await _assert_allocation_absent(database, scenario)
        else:
            assert isinstance(result, ArtifactAllocationDTO)
            assert result.cleanup_binding.origin == scenario.origin


@pytest.mark.asyncio
async def test_unadmitted_stage_reserves_full_bytes_obligation_and_dormant_cleanup_without_product_identity(
    database: Database,
) -> None:
    scenario = artifact_scenario(await seed_artifact_scope(database))
    allocation = await allocate_artifact(database, scenario)
    assert allocation.reservation.limit_bytes == 25 * 1024 * 1024
    assert allocation.cleanup_binding.origin == scenario.origin
    async with database.session() as session:
        row = await session.get(DurableJobRow, allocation.cleanup_job_id.value)
        assert row is not None
        assert row.binding_kind == "artifact_cleanup" and row.operation_id is None
        assert row.principal_id is None and row.action_id is None
        assert row.cleanup_obligation_id == scenario.obligation_id.value
        assert row.status == JobStatus.QUEUED.value and row.attempt_count == 0
        assert row.due_at == allocation.reservation.expires_at
        assert row.queued_deadline == row.admitted_at + timedelta(hours=24)
        assert row.admitted_at < row.due_at <= row.admitted_at + timedelta(hours=2)
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )
        ledger = await session.get(ArtifactStorageCapacityRow, scenario.scope.installation_id.value)
        assert ledger is not None and ledger.spool_reserved_bytes == 25 * 1024 * 1024
        assert ledger.protected_reserved_bytes == 2 * 25 * 1024 * 1024
        audits = (await session.scalars(select(AccessAuditEventRow))).all()
        assert len(audits) == 1 and audits[0].actor_principal_id is None


@pytest.mark.asyncio
async def test_same_allocation_retry_recovers_original_job_deadline_and_single_audit(
    database: Database,
) -> None:
    scenario = artifact_scenario(await seed_artifact_scope(database))
    first = await allocate_artifact(database, scenario)
    second = await allocate_artifact(database, scenario)
    assert second.cleanup_job_id == first.cleanup_job_id
    assert second.reservation.expires_at == first.reservation.expires_at
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ArtifactCleanupObligationRow))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1


@pytest.mark.asyncio
async def test_full_cleanup_queue_rolls_back_new_bytes_attempt_obligation_and_audit(
    database: Database,
) -> None:
    scope = await seed_artifact_scope(database)
    await allocate_artifact(database, artifact_scenario(scope), capacity=1)
    with pytest.raises(JobQueueFullError):
        await allocate_artifact(database, artifact_scenario(scope), capacity=1)
    async with database.session() as session:
        for model in [
            ArtifactAttemptRow,
            ArtifactStagingReservationRow,
            ArtifactCleanupObligationRow,
            DurableJobRow,
            AccessAuditEventRow,
        ]:
            assert await session.scalar(select(func.count()).select_from(model)) == 1
        ledger = await session.get(ArtifactStorageCapacityRow, scope.installation_id.value)
        assert ledger is not None and ledger.spool_reserved_bytes == 25 * 1024 * 1024


@pytest.mark.asyncio
async def test_concurrent_original_cleanup_allocations_cannot_both_take_last_slot(
    database: Database,
) -> None:
    scope = await seed_artifact_scope(database)
    results = await asyncio.gather(
        *(allocate_artifact(database, artifact_scenario(scope), capacity=1) for _ in range(2)),
        return_exceptions=True,
    )
    admitted = [result for result in results if isinstance(result, ArtifactAllocationDTO)]
    assert len(admitted) == 1
    assert sum(isinstance(result, JobQueueFullError) for result in results) == 1
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ArtifactAttemptRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ArtifactCleanupObligationRow))
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 0
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("length", "digest"),
    [(None, b"H" * 32), (0, None), (None, b"H" * 31), (-1, b"H" * 32), (1, b"H" * 31)],
    ids=[
        "missing_length",
        "missing_digest",
        "missing_length_short_digest",
        "negative_length",
        "short_digest",
    ],
)
async def test_invalid_sealed_length_digest_pairs_cannot_persist(
    database: Database, length: int | None, digest: bytes | None
) -> None:
    scenario = artifact_scenario(await seed_artifact_scope(database))
    await allocate_artifact(database, scenario)
    async with database.session() as session, session.begin():
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    update(ArtifactAttemptRow)
                    .where(ArtifactAttemptRow.id == scenario.attempt_id.value)
                    .values(length=length, digest=digest)
                )
        saved = await session.get(ArtifactAttemptRow, scenario.attempt_id.value)
        assert saved is not None and saved.length is None and saved.digest is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("length", "digest"),
    [(None, None), (0, hashlib.sha256(b"").digest())],
    ids=["unsealed", "empty_sealed"],
)
async def test_unsealed_or_valid_zero_length_expectation_remains_supported(
    database: Database, length: int | None, digest: bytes | None
) -> None:
    scenario = artifact_scenario(await seed_artifact_scope(database))
    await allocate_artifact(database, scenario)
    async with database.session() as session, session.begin():
        await session.execute(
            update(ArtifactAttemptRow)
            .where(ArtifactAttemptRow.id == scenario.attempt_id.value)
            .values(length=length, digest=digest)
        )
    async with database.session() as session:
        saved = await session.get(ArtifactAttemptRow, scenario.attempt_id.value)
        assert saved is not None and (saved.length, saved.digest) == (length, digest)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        "fresh_obligation",
        "fresh_obligation_request",
        "same_obligation_request",
        "fresh_business_origin",
        "same_obligation_business_origin",
        "fresh_business_request",
    ],
)
async def test_original_allocation_cannot_rebind_cleanup_identity_or_origin(
    database: Database, changed: str
) -> None:
    alternative_origin = None
    if "business" in changed:
        scope, origin = await completed_product_origin(database)
        scenario = artifact_scenario(scope, origin)
        if "business_origin" in changed:
            same_scope, alternative_origin = await completed_product_origin(database, scope)
            assert same_scope == scope and alternative_origin.operation_id != origin.operation_id
    else:
        scenario = artifact_scenario(await seed_artifact_scope(database))
    first = await allocate_artifact(database, scenario)
    retry = scenario
    if changed.startswith("fresh"):
        retry = replace(retry, obligation_id=ArtifactCleanupObligationId(uuid4()))
    if changed.endswith("request"):
        retry = replace(retry, origin=replace(retry.origin, request_id=RequestId(uuid4())))
    elif alternative_origin is not None:
        retry = replace(retry, origin=alternative_origin)
    with pytest.raises(ArtifactReservationError):
        await allocate_artifact(database, retry)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(DurableJobRow)
                .where(DurableJobRow.binding_kind == "artifact_cleanup")
            )
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(ArtifactCleanupObligationRow))
            == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "artifact_cleanup_admitted")
            )
            == 1
        )
        obligation = await session.get(ArtifactCleanupObligationRow, scenario.obligation_id.value)
        assert obligation is not None and obligation.request_id == scenario.origin.request_id.value
        job = await session.get(DurableJobRow, first.cleanup_job_id.value)
        assert job is not None and job.cleanup_obligation_id == scenario.obligation_id.value


@pytest.mark.asyncio
async def test_concurrent_competing_allocation_meanings_keep_one_original_binding(
    database: Database,
) -> None:
    original = artifact_scenario(await seed_artifact_scope(database))
    competing = replace(
        original,
        obligation_id=ArtifactCleanupObligationId(uuid4()),
        origin=replace(original.origin, request_id=RequestId(uuid4())),
    )
    results = await asyncio.gather(
        allocate_artifact(database, original),
        allocate_artifact(database, competing),
        return_exceptions=True,
    )
    accepted = [result for result in results if isinstance(result, ArtifactAllocationDTO)]
    assert len(accepted) == 1
    assert sum(isinstance(result, ArtifactReservationError) for result in results) == 1
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ArtifactAttemptRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(ArtifactCleanupObligationRow))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1
        job = await session.get(DurableJobRow, accepted[0].cleanup_job_id.value)
        assert (
            job is not None
            and job.cleanup_obligation_id == accepted[0].cleanup_binding.obligation_id.value
        )


@pytest.mark.asyncio
async def test_concurrent_identical_allocation_replays_retain_original_binding(
    database: Database,
) -> None:
    scenario = artifact_scenario(await seed_artifact_scope(database))
    first, second = await asyncio.gather(
        allocate_artifact(database, scenario), allocate_artifact(database, scenario)
    )
    assert first.cleanup_binding == second.cleanup_binding
    assert first.cleanup_job_id == second.cleanup_job_id
    assert first.reservation.expires_at == second.reservation.expires_at
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ArtifactCleanupObligationRow))
            == 1
        )
        assert await session.scalar(select(func.count()).select_from(DurableJobRow)) == 1
        assert await session.scalar(select(func.count()).select_from(AccessAuditEventRow)) == 1


@pytest.mark.asyncio
async def test_distinct_pending_erasure_obligation_can_retain_same_physical_target(
    database: Database,
) -> None:
    scope, origin = await completed_product_origin(database)
    scenario = artifact_scenario(scope, origin)
    allocation = await allocate_artifact(database, scenario)
    erasure = ArtifactCleanupObligationId(uuid4())
    # This is pending inventory, not proof of retirement or executable erasure.
    # Later erasure must remain distinct from the original staging allocation.
    async with database.session() as session, session.begin():
        session.add(
            ArtifactCleanupObligationRow(
                id=erasure.value,
                installation_id=scope.installation_id.value,
                organization_id=scope.organization_id.value,
                project_id=scope.project_id.value,
                kind="erasure",
                origin_kind="business",
                origin_operation_id=origin.operation_id.value,
                request_id=origin.request_id.value,
                transfer_deadline=allocation.reservation.expires_at,
            )
        )
        await session.flush()
        session.add(
            ArtifactCleanupTargetRow(
                obligation_id=erasure.value, attempt_id=scenario.attempt_id.value
            )
        )
    async with database.session() as session:
        targets = tuple(
            await session.scalars(
                select(ArtifactCleanupTargetRow.obligation_id).where(
                    ArtifactCleanupTargetRow.attempt_id == scenario.attempt_id.value
                )
            )
        )
        assert set(targets) == {scenario.obligation_id.value, erasure.value}
        pending = await session.get(ArtifactCleanupObligationRow, erasure.value)
        assert (
            pending is not None
            and not pending.retirement_authorized
            and not pending.physically_complete
        )
