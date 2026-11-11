"""Preserve retired POST identity without retaining its creation-only command."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, update
from tests.support.historical_project_grant_scenarios import (
    RetainedProjectGrantPostDTO,
    seed_retained_project_grant_post,
)
from tests.support.project_action_grant_postgres_scenarios import (
    change_project_grant,
)

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.unresolved_operation_dto import (
    UnresolvedOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]
ACTION = ActionId("create-access-groups")
HISTORICAL_ROUTE = "/v1/projects/{project_id}/grants"


async def _effects(
    database: Database, retained: RetainedProjectGrantPostDTO
) -> tuple[int | None, int | None, int | None, int | None]:
    async with database.session() as session:
        return (
            await session.scalar(
                select(ProjectRow.access_revision).where(
                    ProjectRow.id == retained.seed.project.project_id.value
                )
            ),
            await session.scalar(select(func.count()).select_from(ProjectActionGrantRow)),
            await session.scalar(select(func.count()).select_from(AccessAuditEventRow)),
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)),
        )


async def test_retired_post_lookup_keeps_original_binding_fingerprint_expiry_and_outcome(
    database: Database,
) -> None:
    retained = await seed_retained_project_grant_post(database)
    before = await _effects(database, retained)
    for _ in range(2):
        async with open_original_operation_lookup(database) as lookup:
            result = await lookup.lookup(access=retained.seed.actor.access, query=retained.query)
        assert result == CompletedSynchronousOperationDTO(
            operation_id=retained.operation_id,
            created=False,
            replay_kind=OperationReplayKind.SAFE_RESULT,
            expires_at=retained.expires_at,
        )
    assert await _effects(database, retained) == before
    async with database.session() as session:
        row = await session.get(IdempotencyReservationRow, retained.operation_id.value)
        assert row is not None
        assert (
            row.principal_id,
            row.organization_id,
            row.project_id,
            row.method,
            row.requested_route,
            row.request_key,
            row.request_fingerprint,
            row.expires_at,
            row.state,
            row.replay_kind,
            row.lookup_authority_family,
            row.lookup_action_id,
        ) == (
            retained.seed.actor.access.actor_principal_id.value,
            retained.seed.actor.organization_id.value,
            retained.seed.project.project_id.value,
            "POST",
            HISTORICAL_ROUTE,
            retained.query.key.value,
            retained.fingerprint,
            retained.expires_at,
            OperationReservationState.REPLAYABLE,
            OperationReplayKind.SAFE_RESULT,
            "project_grant_read",
            ACTION.value,
        )


@pytest.mark.parametrize("change", ["key", "method"])
async def test_retired_post_unknown_identity_is_unresolved_without_dispatch_or_effects(
    database: Database, change: str
) -> None:
    retained = await seed_retained_project_grant_post(database)
    before = await _effects(database, retained)
    if change == "key":
        query = replace(retained.query, key=IdempotencyKey("unknown-original"))
    else:
        query = replace(
            retained.query,
            method=HttpMethod.PUT,
            requested_route=f"/v1/projects/{retained.seed.project.project_id.value}/grants/{retained.seed.bob_id.value}/{ACTION.value}",
        )
    async with open_original_operation_lookup(database) as lookup:
        assert isinstance(
            await lookup.lookup(access=retained.seed.actor.access, query=query),
            UnresolvedOperationDTO,
        )
    assert await _effects(database, retained) == before


async def test_retired_post_expiry_is_unresolved_and_never_extended(database: Database) -> None:
    retained = await seed_retained_project_grant_post(database)
    expired = datetime.now(UTC) - timedelta(hours=1)
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == retained.operation_id.value)
            .values(expires_at=expired)
        )
    before = await _effects(database, retained)
    async with open_original_operation_lookup(database) as lookup:
        assert isinstance(
            await lookup.lookup(access=retained.seed.actor.access, query=retained.query),
            UnresolvedOperationDTO,
        )
    assert await _effects(database, retained) == before
    async with database.session() as session:
        assert (
            await session.scalar(
                select(IdempotencyReservationRow.expires_at).where(
                    IdempotencyReservationRow.operation_id == retained.operation_id.value
                )
            )
            == expired
        )


async def test_retired_post_metadata_requires_current_exact_delegation_and_original_initiator(
    database: Database,
) -> None:
    retained = await seed_retained_project_grant_post(database)
    seed = retained.seed
    await change_project_grant(
        database, seed, revision=2, key="delegate-bob", action_id=ACTION, can_grant=True
    )
    bob = seed.bob_access
    async with open_original_operation_lookup(database) as lookup:
        assert isinstance(
            await lookup.lookup(access=bob, query=retained.query), UnresolvedOperationDTO
        )
    await change_project_grant(
        database,
        seed,
        revision=3,
        key="downgrade-original-initiator",
        action_id=ACTION,
        recipient=seed.actor.access.actor_principal_id,
        can_grant=False,
        access=bob,
    )
    before = await _effects(database, retained)
    async with open_original_operation_lookup(database) as lookup:
        with pytest.raises(AccessDeniedError):
            await lookup.lookup(access=seed.actor.access, query=retained.query)
    assert await _effects(database, retained) == before


async def test_retired_post_concrete_route_cannot_reinterpret_original_literal_binding(
    database: Database,
) -> None:
    retained = await seed_retained_project_grant_post(database)
    before = await _effects(database, retained)
    query = replace(
        retained.query,
        requested_route=f"/v1/projects/{retained.seed.project.project_id.value}/grants",
    )
    async with open_original_operation_lookup(database) as lookup:
        with pytest.raises(InvalidInputError):
            await lookup.lookup(access=retained.seed.actor.access, query=query)
    assert await _effects(database, retained) == before
