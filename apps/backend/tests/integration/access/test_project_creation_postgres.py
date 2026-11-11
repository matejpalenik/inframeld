"""Verify creation atomicity, current authority and immutable retries in real PostgreSQL."""

import asyncio
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Never, override
from uuid import uuid4

import pytest
from sqlalchemy import Integer, String, column, delete, event, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.project_creation_scenarios import (
    assert_created_project,
    create_project,
    creation_command,
    creation_context,
    creation_service,
    seed_project_creator,
)
from tests.support.project_metadata_scenarios import metadata_service

from inframeld_backend.access.application.commands.update_project_metadata_command import (
    UpdateProjectMetadataCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.project_creation_result_dto import (
    ProjectCreationResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_creation_operation_result_row import (
    ProjectCreationOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.bootstrap.organization_access_composition import open_my_organization_access
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def _assert_no_creation(database: Database) -> None:
    async with database.session() as session:
        for row in (
            ProjectRow,
            ProjectMembershipRow,
            ProjectActionGrantRow,
            ProjectNameReservationRow,
            ProjectCreationOperationResultRow,
            IdempotencyReservationRow,
        ):
            assert await session.scalar(select(func.count()).select_from(row)) == 0
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "project_created")
            )
            == 0
        )
        assert await session.scalar(select(OrganizationRow.access_revision)) == 1


async def _wait_for_org_lock(
    database: Database, task: asyncio.Task[ProjectCreationResultDTO]
) -> None:
    """Observe an actual PostgreSQL lock wait before altering the preceding transaction."""
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(3):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        func.cardinality(
                            func.pg_blocking_pids(pid, type_=ARRAY(Integer)), type_=Integer
                        )
                        > 0,
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)
    task.result()
    pytest.fail("Creation bypassed the required Organization lock.")


async def test_own_access_reports_actual_empty_assignments_without_create_authority(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    async with database.session() as session, session.begin():
        await session.execute(delete(OrganizationActionGrantRow))
    async with open_my_organization_access(database) as reader:
        access = await reader.read(access=seed.access)
    assert access.organization_id == seed.organization_id
    assert access.principal_id == seed.access.actor_principal_id
    assert access.access_revision == 1 and access.grants == ()
    with pytest.raises(AccessDeniedError):
        await create_project(database, seed)
    await _assert_no_creation(database)


async def test_create_projects_use_only_grant_creates_multiple_ordinary_projects(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    async with database.session() as session, session.begin():
        await session.execute(
            update(OrganizationActionGrantRow)
            .where(OrganizationActionGrantRow.action == "create-projects")
            .values(can_grant=False)
        )
    async with open_my_organization_access(database) as reader:
        own = await reader.read(access=seed.access)
    assert {item.action_id.value: item.can_grant for item in own.grants} == {
        "admit-users": True,
        "create-projects": False,
        "restore-users": True,
        "suspend-users": True,
    }
    first = await create_project(database, seed)
    second = await create_project(database, seed, name="legal", key="second")
    assert first.project.project_id != second.project.project_id
    await assert_created_project(database, first)
    await assert_created_project(database, second)


async def test_original_result_survives_rename_removed_grants_and_changed_org_revision(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await create_project(database, seed)
    async with database.session() as session:
        await metadata_service(session).update(
            access=seed.access,
            command=UpdateProjectMetadataCommand(
                first.project.project_id,
                0,
                ResourceName("renamed"),
                SubmittedDisplayName("Renamed"),
            ),
            context=IdempotencyContextDTO(
                HttpMethod.PATCH, "/v1/projects/{project_id}/metadata", IdempotencyKey("rename")
            ),
        )
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == first.project.project_id.value,
                ProjectActionGrantRow.action == "create-pipelines",
            )
        )
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == first.project.project_id.value)
            .values(access_revision=2)
        )
        await session.execute(update(OrganizationRow).values(access_revision=9))
    replay = await create_project(database, seed)
    assert replay.project == first.project and not replay.operation.created
    assert replay.operation.operation_id == first.operation.operation_id
    assert replay.operation.expires_at == first.operation.expires_at
    async with database.session() as session:
        project = await session.get(ProjectRow, first.project.project_id.value)
        assert project is not None
        assert (
            project.resource_name,
            project.name,
            project.access_revision,
            project.metadata_revision,
        ) == ("renamed", "Renamed", 2, 1)
        assert await session.scalar(select(func.count()).select_from(ProjectActionGrantRow)) == 17
        assert await session.scalar(select(OrganizationRow.access_revision)) == 9
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "project_created")
            )
            == 1
        )
    with pytest.raises(ConflictError):
        await create_project(database, seed, name="different")
    with pytest.raises(StaleRevisionError):
        await create_project(database, seed, name="fresh", key="new")


async def test_current_create_authority_is_required_before_original_replay(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await create_project(database, seed)
    async with database.session() as session, session.begin():
        await session.execute(
            delete(OrganizationActionGrantRow).where(
                OrganizationActionGrantRow.action == "create-projects"
            )
        )
    with pytest.raises(AccessDeniedError):
        await create_project(database, seed)
    await assert_created_project(database, first)


async def test_stale_new_creation_rolls_back_its_reservation(database: Database) -> None:
    seed = await seed_project_creator(database)
    async with database.session() as session:
        with pytest.raises(StaleRevisionError):
            await creation_service(session).create(
                access=seed.access,
                command=replace(creation_command(seed), expected_access_revision=0),
                context=creation_context(),
            )
    await _assert_no_creation(database)


class FailingCompletionIdempotency(IdempotencyService):
    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> Never:
        await super().record_completed_result(operation, replay_kind=replay_kind)
        raise RuntimeError("Controlled completion failure")


@pytest.mark.parametrize("failure", ["audit", "completion", "cancellation"])
async def test_required_write_failure_rolls_back_project_grants_name_audit_and_receipt(
    database: Database, failure: str
) -> None:
    seed = await seed_project_creator(database)

    def reject_required_write(session: Session, _context: object, _instances: object) -> None:
        if any(
            isinstance(row, AccessAuditEventRow) and row.event_type == "project_created"
            for row in session.new
        ):
            if failure == "cancellation":
                raise asyncio.CancelledError()
            raise RuntimeError("Controlled audit failure")

    async with database.session() as session:
        if failure != "completion":
            event.listen(session.sync_session, "before_flush", reject_required_write)
        try:
            error = asyncio.CancelledError if failure == "cancellation" else RuntimeError
            idempotency = (
                FailingCompletionIdempotency(PostgresOperationReservationWriter(session))
                if failure == "completion"
                else None
            )
            with pytest.raises(error):
                await creation_service(session, idempotency).create(
                    access=seed.access, command=creation_command(seed), context=creation_context()
                )
        finally:
            if failure != "completion":
                event.remove(session.sync_session, "before_flush", reject_required_write)
    await _assert_no_creation(database)


@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_same_name_preserves_one_complete_original_creation(
    database: Database, same_key: bool
) -> None:
    seed = await seed_project_creator(database)

    async def create(key: str) -> ProjectCreationResultDTO | ConflictError:
        try:
            return await create_project(database, seed, key=key)
        except ConflictError as error:
            return error

    async with asyncio.timeout(12), asyncio.TaskGroup() as tasks:
        first = tasks.create_task(create("first"))
        second = tasks.create_task(create("first" if same_key else "second"))
    results = [item.result() for item in (first, second)]
    successes = [item for item in results if isinstance(item, ProjectCreationResultDTO)]
    assert len(successes) == (2 if same_key else 1)
    original = successes[0]
    if same_key:
        assert successes[1].project == original.project
        assert successes[1].operation.operation_id == original.operation.operation_id
        assert successes[1].operation.expires_at == original.operation.expires_at
        assert sorted(item.operation.created for item in successes) == [False, True]
    else:
        assert sum(isinstance(item, ConflictError) for item in results) == 1
    await assert_created_project(database, original)
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow)) == 1
        )


async def test_expired_creation_key_creates_new_work_without_reusing_original_name(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await create_project(database, seed)
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == first.operation.operation_id.value)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    with pytest.raises(ConflictError):
        await create_project(database, seed)
    async with database.session() as session:
        receipt = await session.get(
            ProjectCreationOperationResultRow, first.operation.operation_id.value
        )
        assert receipt is not None and receipt.project_id == first.project.project_id.value
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 1
    replacement = await create_project(database, seed, name="fresh")
    assert replacement.operation.created
    assert replacement.operation.operation_id != first.operation.operation_id
    assert replacement.project.project_id != first.project.project_id
    await assert_created_project(database, replacement)
    async with database.session() as session:
        assert (
            await session.get(ProjectCreationOperationResultRow, first.operation.operation_id.value)
            is None
        )
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 2


async def test_recovery_committing_before_creation_is_observed_after_real_org_lock_wait(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    task: asyncio.Task[ProjectCreationResultDTO] | None = None
    async with asyncio.timeout(12), database.session() as holder:
        try:
            async with holder.begin():
                await holder.scalar(
                    select(OrganizationRow)
                    .where(OrganizationRow.id == seed.organization_id.value)
                    .with_for_update()
                )
                holder.add(
                    IdentityRecoveryAdmissionRow(
                        operation_id="pending-recovery",
                        installation_id=seed.binding.installation_id.value,
                        authority=seed.binding.identity.authority.value,
                        subject=seed.binding.identity.subject.value,
                        flow_id=uuid4(),
                        event_kind=IdentityRecoveryEventKind.RECOVERY,
                    )
                )
                await holder.flush()
                task = asyncio.create_task(create_project(database, seed))
                await _wait_for_org_lock(database, task)
            with pytest.raises(AccessDeniedError):
                await task
        finally:
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    await _assert_no_creation(database)


async def test_held_organization_lock_times_out_without_partial_creation(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    task: asyncio.Task[ProjectCreationResultDTO] | None = None
    async with asyncio.timeout(9), database.session() as holder:
        try:
            async with holder.begin():
                await holder.scalar(
                    select(OrganizationRow.id)
                    .where(OrganizationRow.id == seed.organization_id.value)
                    .with_for_update()
                )
                task = asyncio.create_task(create_project(database, seed))
                await _wait_for_org_lock(database, task)
                with pytest.raises(DependencyUnavailableError):
                    await task
        finally:
            if task is not None:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)
    await _assert_no_creation(database)


async def test_stale_oauth_generation_cannot_read_or_replay_original_creation(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    seed = replace(seed, access=AccessContextDTO(seed.access.actor_principal_id, seed.binding))
    first = await create_project(database, seed)
    async with database.session() as session, session.begin():
        await session.execute(
            update(HumanCredentialVersionRow)
            .where(
                HumanCredentialVersionRow.installation_id == seed.binding.installation_id.value,
                HumanCredentialVersionRow.authority == seed.binding.identity.authority.value,
                HumanCredentialVersionRow.subject == seed.binding.identity.subject.value,
            )
            .values(version=seed.binding.version.value + 1)
        )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await create_project(database, seed)
    with pytest.raises(HumanOAuthCredentialRejectedError):
        async with open_my_organization_access(database) as reader:
            await reader.read(access=seed.access)
    await assert_created_project(database, first)


async def test_current_and_retired_names_conflict_only_within_their_organization(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await create_project(database, seed)
    async with database.session() as session:
        await metadata_service(session).update(
            access=seed.access,
            command=UpdateProjectMetadataCommand(
                first.project.project_id, 0, ResourceName("current")
            ),
            context=IdempotencyContextDTO(
                HttpMethod.PATCH, "/v1/projects/{project_id}/metadata", IdempotencyKey("rename")
            ),
        )
    for name in ("support", "current"):
        with pytest.raises(ConflictError):
            await create_project(database, seed, name=name, key=f"collision-{name}")
    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
    )
    async with database.session() as session, session.begin():
        other = await MockAccessScenarios.seed_linked_human(session, identity)
        session.add(
            OrganizationActionGrantRow(
                organization_id=other.organization_id.value,
                recipient_principal_id=other.id.value,
                action="create-projects",
                recipient_kind=PrincipalKind.HUMAN,
                can_grant=False,
            )
        )
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    access = AccessContextDTO(
        other.id, BrowserSessionAuthenticationDTO(identity, state.installation_id, state.version)
    )
    async with database.session() as session:
        result = await creation_service(session).create(
            access=access,
            command=replace(
                creation_command(seed),
                organization_id=other.organization_id,
                expected_access_revision=0,
            ),
            context=creation_context(),
        )
    assert result.project.organization_id == other.organization_id
    assert result.project.name.value == "support"
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ProjectRow)) == 2
        assert await session.scalar(select(func.count()).select_from(ProjectActionGrantRow)) == 36
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectCreationOperationResultRow)
            )
            == 2
        )
