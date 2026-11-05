"""Verify actual metadata transitions, original outcomes and collision rollback."""

import asyncio
import os

import pytest
from sqlalchemy import delete, func, select, update
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_metadata_scenarios import (
    metadata_service,
    seed_another_metadata_project,
    seed_metadata_project,
)

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


def context(key: str) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        HttpMethod.PATCH, "/v1/projects/{project_id}/metadata", IdempotencyKey(key)
    )


@pytest.mark.asyncio
async def test_original_metadata_outcome_survives_later_rename_and_retired_name_stays_unavailable(
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        seed = await seed_metadata_project(session)
        other = await seed_another_metadata_project(session, seed)
    access = AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser())
    original = UpdateProjectMetadataCommand(seed.project_id, 0, ResourceName("support"))
    async with database.session() as session:
        first = await metadata_service(session).update(
            access=access, command=original, context=context("original")
        )
    async with database.session() as session:
        await metadata_service(session).update(
            access=access,
            command=UpdateProjectMetadataCommand(
                seed.project_id, 1, ResourceName("legal"), SubmittedDisplayName("Legal")
            ),
            context=context("rename"),
        )
    async with database.session() as session:
        replay = await metadata_service(session).update(
            access=access, command=original, context=context("original")
        )
    assert replay.metadata == first.metadata
    assert replay.operation.operation_id == first.operation.operation_id
    assert replay.operation.expires_at == first.operation.expires_at
    async with database.session() as session:
        with pytest.raises(ConflictError):
            await metadata_service(session).update(
                access=access,
                command=UpdateProjectMetadataCommand(
                    other.project_id, 0, ResourceName("support"), SubmittedDisplayName("Changed")
                ),
                context=context("collision"),
            )
    async with database.session() as session:
        untouched = await session.get(ProjectRow, other.project_id.value)
        assert untouched is not None
        assert (untouched.resource_name, untouched.name, untouched.metadata_revision) == (
            None,
            "Other",
            0,
        )


@pytest.mark.asyncio
async def test_concurrent_exact_name_collision_commits_one_complete_change(
    database: Database,
) -> None:
    async with database.session() as session, session.begin():
        first = await seed_metadata_project(session)
        second = await seed_another_metadata_project(session, first)
    access = AccessContextDTO(first.principal_id, MockAuthenticationEvidence.browser())

    async def allocate(seed_id: ProjectId):
        async with database.session() as session:
            return await metadata_service(session).update(
                access=access,
                command=UpdateProjectMetadataCommand(
                    seed_id, 0, ResourceName("shared"), SubmittedDisplayName("Changed")
                ),
                context=context("allocate"),
            )

    outcomes = await asyncio.gather(
        allocate(first.project_id), allocate(second.project_id), return_exceptions=True
    )
    assert sum(not isinstance(result, BaseException) for result in outcomes) == 1
    assert sum(isinstance(result, ConflictError) for result in outcomes) == 1
    async with database.session() as session:
        rows = (
            await session.scalars(
                select(ProjectRow).where(
                    ProjectRow.id.in_((first.project_id.value, second.project_id.value))
                )
            )
        ).all()
        assert sorted(row.metadata_revision for row in rows) == [0, 1]
        assert (
            await session.scalar(select(func.count()).select_from(ProjectNameReservationRow)) == 1
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "project_metadata_changed")
            )
            == 1
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", ["", " ", "a" * 1000, "legacy\x01\nlabel"])
async def test_selector_only_change_preserves_legacy_label_in_current_and_original_result(
    database: Database, legacy: str
) -> None:
    async with database.session() as session, session.begin():
        seed = await seed_metadata_project(session)
        await session.execute(
            update(ProjectRow).where(ProjectRow.id == seed.project_id.value).values(name=legacy)
        )
    access = AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser())
    command = UpdateProjectMetadataCommand(seed.project_id, 0, ResourceName("support"))
    async with database.session() as session:
        result = await metadata_service(session).update(
            access=access, command=command, context=context("legacy")
        )
    async with database.session() as session:
        replay = await metadata_service(session).update(
            access=access, command=command, context=context("legacy")
        )
        stored = await session.get(ProjectRow, seed.project_id.value)
        assert stored is not None
        assert stored.name == result.metadata.display_name == replay.metadata.display_name == legacy
        assert stored.resource_name == "support"


@pytest.mark.asyncio
async def test_stale_change_and_revoked_replay_cannot_mutate_or_disclose_original_result(
    database: Database,
) -> None:
    from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
        ProjectActionGrantRow,
    )
    from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
        IdempotencyReservationRow,
    )

    async with database.session() as session, session.begin():
        seed = await seed_metadata_project(session)
    access = AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser())
    original = UpdateProjectMetadataCommand(seed.project_id, 0, ResourceName("support"))
    async with database.session() as session:
        await metadata_service(session).update(
            access=access, command=original, context=context("original")
        )
    async with database.session() as session:
        with pytest.raises(StaleRevisionError):
            await metadata_service(session).update(
                access=access,
                command=UpdateProjectMetadataCommand(
                    seed.project_id, 0, ResourceName("legal"), SubmittedDisplayName("Legal")
                ),
                context=context("stale"),
            )
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == seed.project_id.value,
                ProjectActionGrantRow.action == "edit-project-metadata",
            )
        )
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == seed.project_id.value)
            .values(access_revision=ProjectRow.access_revision + 1)
        )
    async with database.session() as session:
        with pytest.raises(AccessDeniedError):
            await metadata_service(session).update(
                access=access, command=original, context=context("original")
            )
    async with database.session() as session:
        row = await session.get(ProjectRow, seed.project_id.value)
        assert row is not None
        assert (row.resource_name, row.name, row.metadata_revision) == ("support", "Support", 1)
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.project_id == seed.project_id.value)
            )
            == 1
        )


@pytest.mark.asyncio
async def test_actual_audit_flush_failure_rolls_back_metadata_name_result_and_reservation(
    database: Database,
) -> None:
    from typing import override

    from inframeld_backend.access.application.dtos.project_metadata_changed_audit_event_dto import (
        ProjectMetadataChangedAuditEventDTO,
    )
    from inframeld_backend.access.infrastructure.rows.project_metadata_operation_result_row import (
        ProjectMetadataOperationResultRow,
    )
    from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
        PostgresProjectMetadataAuditWriter,
    )
    from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
        IdempotencyReservationRow,
    )

    class MockFailingAudit(PostgresProjectMetadataAuditWriter):
        @override
        async def changed(self, event: ProjectMetadataChangedAuditEventDTO) -> None:
            await super().changed(event)
            raise RuntimeError("Audit storage failed before commit.")

    async with database.session() as session, session.begin():
        seed = await seed_metadata_project(session)
    access = AccessContextDTO(seed.principal_id, MockAuthenticationEvidence.browser())
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="Audit storage failed"):
            await metadata_service(session, MockFailingAudit(session)).update(
                access=access,
                command=UpdateProjectMetadataCommand(
                    seed.project_id, 0, ResourceName("support"), SubmittedDisplayName("Changed")
                ),
                context=context("rollback"),
            )
    async with database.session() as session:
        row = await session.get(ProjectRow, seed.project_id.value)
        assert row is not None
        assert (row.resource_name, row.name, row.metadata_revision) == (None, "Support", 0)
        for table in (
            ProjectNameReservationRow,
            ProjectMetadataOperationResultRow,
            IdempotencyReservationRow,
            AccessAuditEventRow,
        ):
            assert await session.scalar(select(func.count()).select_from(table)) == 0
