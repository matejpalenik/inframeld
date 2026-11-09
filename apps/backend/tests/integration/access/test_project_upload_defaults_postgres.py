"""Qualify future-default persistence and its trusted admission projection on real Access rows."""

import asyncio
import os
from datetime import timedelta
from typing import override
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import DateTime, Integer, String, column, delete, event, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Session
from tests.support.access_group_scenarios import change_group, delete_group, group_fingerprints
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_upload_default_scenarios import (
    UploadDefaultScenario,
    replace_upload_default,
    seed_upload_default_scenario,
    upload_default_context,
    upload_default_effects,
    upload_default_service,
)

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_deletion_result_dto import (
    AccessGroupDeletionResultDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_change_result_dto import (
    ProjectUploadDefaultChangeResultDTO,
)
from inframeld_backend.access.application.dtos.project_upload_default_record_dto import (
    ProjectUploadDefaultRecordDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.queries.get_project_upload_default_query import (
    GetProjectUploadDefaultQuery,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.application.services.project_upload_default_fingerprint_service import (
    ProjectUploadDefaultFingerprintService,
)
from inframeld_backend.access.application.services.project_upload_default_service import (
    ProjectUploadDefaultService,
)
from inframeld_backend.access.domain.entities.project_upload_default import ProjectUploadDefault
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_upload_default_facts_reader import (
    PostgresProjectUploadDefaultFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_upload_default_repository import (
    PostgresProjectUploadDefaultRepository,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.project_upload_default_group_row import (
    ProjectUploadDefaultGroupRow,
)
from inframeld_backend.access.infrastructure.rows.project_upload_default_result_row import (
    ProjectUploadDefaultResultRow,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
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
        reason="Requires isolated PostgreSQL integration services",
    ),
]


@pytest_asyncio.fixture
async def scope(database: Database) -> UploadDefaultScenario:
    return await seed_upload_default_scenario(database)


def _command(
    scope: UploadDefaultScenario, indexes: tuple[int, ...] = (0,), revision: int | None = None
) -> SetProjectUploadDefaultCommand:
    return SetProjectUploadDefaultCommand(
        scope.project_id,
        UploadAudience(tuple(scope.groups[i].group_id for i in indexes)),
        scope.revision if revision is None else revision,
    )


async def test_valid_project_with_zero_links_is_unconfigured(
    database: Database, scope: UploadDefaultScenario
) -> None:
    async with database.session() as session, session.begin():
        observed = await PostgresProjectUploadDefaultFactsReader(session).read_upload_audience(
            organization_id=scope.actor.organization_id, project_id=scope.project_id
        )
        assert observed.audience is None
        assert observed.access_revision == scope.revision
        assert observed.project_id == scope.project_id


@pytest.mark.parametrize("foreign", [False, True], ids=["missing-project", "foreign-organization"])
async def test_projection_does_not_turn_missing_scope_into_unconfigured(
    database: Database, scope: UploadDefaultScenario, foreign: bool
) -> None:
    async with database.session() as session, session.begin():
        with pytest.raises(ResourceNotFoundError):
            await PostgresProjectUploadDefaultFactsReader(session).read_upload_audience(
                organization_id=OrganizationId(uuid4()) if foreign else scope.actor.organization_id,
                project_id=scope.project_id if foreign else ProjectId(uuid4()),
            )


async def test_current_authoritative_read_observes_saved_groups(
    database: Database, scope: UploadDefaultScenario
) -> None:
    async with database.session() as session, session.begin():
        session.add(
            ProjectUploadDefaultGroupRow(
                organization_id=scope.actor.organization_id.value,
                project_id=scope.project_id.value,
                group_id=scope.groups[0].group_id.value,
            )
        )
    async with database.session() as session:
        result = await upload_default_service(session).get(
            access=scope.actor.access, query=GetProjectUploadDefaultQuery(scope.project_id)
        )
    assert result.audience == UploadAudience((scope.groups[0].group_id,))
    assert result.access_revision == scope.revision


@pytest.mark.parametrize("isolation", ["REPEATABLE READ", "SERIALIZABLE"])
async def test_default_projection_refuses_noncurrent_isolation(
    database: Database, scope: UploadDefaultScenario, isolation: str
) -> None:
    async with database.session() as session:
        await session.connection(execution_options={"isolation_level": isolation})
        try:
            with pytest.raises(RuntimeError, match="READ COMMITTED"):
                await PostgresProjectUploadDefaultFactsReader(session).read_upload_audience(
                    organization_id=scope.actor.organization_id, project_id=scope.project_id
                )
        finally:
            await session.rollback()


async def test_default_reader_requires_callers_transaction(
    database: Database, scope: UploadDefaultScenario
) -> None:
    async with database.session() as session:
        with pytest.raises(RuntimeError, match="transaction"):
            await PostgresProjectUploadDefaultFactsReader(session).read(
                access=scope.actor.access, project_id=scope.project_id
            )


async def test_absent_original_uses_an_authentic_completed_reservation(
    database: Database, scope: UploadDefaultScenario
) -> None:
    command = _command(scope)
    async with database.session() as session, session.begin():
        authorization = await ActionAuthorizationService(
            PostgresProjectActionFactsReader(session)
        ).require_authorization(
            access=scope.actor.access,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=scope.project_id, action_id=ActionId("manage-upload-defaults")
            ),
        )
        idem = IdempotencyService(PostgresOperationReservationWriter(session))
        fingerprint = ProjectUploadDefaultFingerprintService(group_fingerprints()).for_set(command)
        operation = await idem.reserve_or_recover(
            context=upload_default_context(scope.project_id),
            access=scope.actor.access,
            authorization=authorization,
            fingerprint=fingerprint,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        assert isinstance(operation, NewOperationReservationDTO)
        completed = await idem.record_completed_result(
            operation, replay_kind=OperationReplayKind.SAFE_RESULT
        )
        assert isinstance(completed, CompletedSynchronousOperationDTO)
        assert (
            await PostgresProjectUploadDefaultRepository(session).original(
                organization_id=scope.actor.organization_id,
                project_id=scope.project_id,
                actor_principal_id=scope.actor.access.actor_principal_id,
                operation=completed,
            )
            is None
        )


async def test_atomic_writer_accepts_real_new_reservation(
    database: Database, scope: UploadDefaultScenario
) -> None:
    command = _command(scope)
    async with database.session() as session, session.begin():
        authorization = await ActionAuthorizationService(
            PostgresProjectActionFactsReader(session)
        ).require_authorization(
            access=scope.actor.access,
            request=ProjectActionAuthorizationRequestDTO(
                project_id=scope.project_id, action_id=ActionId("manage-upload-defaults")
            ),
        )
        idem = IdempotencyService(PostgresOperationReservationWriter(session))
        fingerprint = ProjectUploadDefaultFingerprintService(group_fingerprints()).for_set(command)
        operation = await idem.reserve_or_recover(
            context=upload_default_context(scope.project_id),
            access=scope.actor.access,
            authorization=authorization,
            fingerprint=fingerprint,
            expected_replay_kind=OperationReplayKind.SAFE_RESULT,
        )
        assert isinstance(operation, NewOperationReservationDTO)
        default = ProjectUploadDefault(
            organization_id=scope.actor.organization_id,
            project_id=scope.project_id,
            audience=None,
            access_revision=scope.revision,
        )
        assert default.replace(audience=command.audience, expected_access_revision=scope.revision)
        original = ProjectUploadDefaultRecordDTO(
            operation.operation_id,
            scope.actor.organization_id,
            scope.project_id,
            scope.actor.access.actor_principal_id,
            scope.revision,
            scope.revision + 1,
            None,
            command.audience,
        )
        await PostgresProjectUploadDefaultRepository(session).save(
            default, original=original, fingerprint=fingerprint
        )
        await idem.record_completed_result(operation, replay_kind=OperationReplayKind.SAFE_RESULT)
    assert await upload_default_effects(database, scope.project_id) == (
        (scope.groups[0].group_id.value,),
        scope.revision + 1,
        1,
        1,
        1,
    )


async def test_service_commits_default_revision_audit_and_original_together(
    database: Database, scope: UploadDefaultScenario
) -> None:
    result = await replace_upload_default(database, scope, (0, 1), scope.revision)
    wanted = tuple(sorted((scope.groups[0].group_id.value, scope.groups[1].group_id.value)))
    assert await upload_default_effects(database, scope.project_id) == (
        wanted,
        scope.revision + 1,
        1,
        1,
        1,
    )
    async with database.session() as session:
        original = await session.get(
            ProjectUploadDefaultResultRow, result.operation.operation_id.value
        )
        assert original is not None
        assert original.before_group_ids is None
        assert tuple(original.group_ids) == wanted
        assert (original.before_revision, original.access_revision) == (
            scope.revision,
            scope.revision + 1,
        )
        audit = await session.scalar(
            select(AccessAuditEventRow).where(
                AccessAuditEventRow.correlation_id == result.operation.operation_id.value
            )
        )
        assert audit is not None
        assert audit.project_id == scope.project_id.value
        assert audit.actor_principal_id == scope.actor.access.actor_principal_id.value


@pytest.mark.parametrize("stale", [False, True])
async def test_fresh_equal_set_checks_revision_before_noop(
    database: Database, scope: UploadDefaultScenario, stale: bool
) -> None:
    first = await replace_upload_default(database, scope, (0,), scope.revision)
    if stale:
        before = await upload_default_effects(database, scope.project_id)
        with pytest.raises(StaleRevisionError):
            await replace_upload_default(database, scope, (0,), scope.revision, "stale-same-set")
        assert await upload_default_effects(database, scope.project_id) == before
    else:
        result = await replace_upload_default(
            database, scope, (0,), first.default.access_revision, "fresh-noop"
        )
        assert result.default.access_revision == first.default.access_revision
        effects = await upload_default_effects(database, scope.project_id)
        assert effects[1:] == (first.default.access_revision, 1, 2, 2)


@pytest.mark.parametrize("missing", [False, True], ids=["retained-old-group", "new-group"])
async def test_management_of_destination_alone_cannot_bypass_old_or_retained_group(
    database: Database, scope: UploadDefaultScenario, missing: bool
) -> None:
    initial = await replace_upload_default(database, scope, (0,), scope.revision)
    target = scope.groups[1 if missing else 0]
    appointed = await change_group(
        database,
        scope.actor.access,
        target,
        scope.bob_id,
        AccessGroupChangeKind.APPOINT_MANAGER,
        initial.default.access_revision,
        "handover",
    )
    removed = await change_group(
        database,
        scope.actor.access,
        target,
        scope.actor.access.actor_principal_id,
        AccessGroupChangeKind.REMOVE_MANAGER,
        appointed.access_revision,
        "remove-manager",
    )
    before = await upload_default_effects(database, scope.project_id)
    with pytest.raises(AccessDeniedError):
        await replace_upload_default(database, scope, (0, 1), removed.access_revision, "denied")
    assert await upload_default_effects(database, scope.project_id) == before


async def test_nonadministrative_admission_projection_does_not_require_manage_defaults(
    database: Database, scope: UploadDefaultScenario
) -> None:
    changed = await replace_upload_default(database, scope, (0,), scope.revision)
    async with database.session() as session, session.begin():
        session.add(
            GroupActionGrantRow(
                project_id=scope.project_id.value,
                group_id=scope.groups[0].group_id.value,
                recipient_principal_id=scope.bob_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action="add-documents",
                can_grant=False,
            )
        )
    bob = AccessContextDTO(
        scope.bob_id,
        MockAuthenticationEvidence.browser(
            VerifiedHumanIdentityDTO(
                scope.actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
            )
        ),
    )
    async with database.session() as session:
        with pytest.raises(AccessDeniedError):
            await upload_default_service(session).get(
                access=bob, query=GetProjectUploadDefaultQuery(scope.project_id)
            )
    async with database.session() as session, session.begin():
        assert (
            await session.scalar(
                select(ProjectActionGrantRow.project_id).where(
                    ProjectActionGrantRow.project_id == scope.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == scope.bob_id.value,
                    ProjectActionGrantRow.action == "manage-upload-defaults",
                )
            )
            is None
        )
        observed = await PostgresProjectUploadDefaultFactsReader(session).read_upload_audience(
            organization_id=scope.actor.organization_id, project_id=scope.project_id
        )
        assert observed.audience == changed.default.audience
        assert observed.access_revision == changed.default.access_revision


@pytest.mark.parametrize("lost", [0, 1, 2], ids=["old-A", "destination-B", "current-C"])
async def test_historical_a_to_b_after_c_rechecks_only_current_c_union_b(
    database: Database, scope: UploadDefaultScenario, lost: int
) -> None:
    revision = scope.revision
    for index, group in enumerate(scope.groups):
        appointed = await change_group(
            database,
            scope.actor.access,
            group,
            scope.bob_id,
            AccessGroupChangeKind.APPOINT_MANAGER,
            revision,
            f"appoint-{index}",
        )
        revision = appointed.access_revision
    a = await replace_upload_default(database, scope, (0,), revision, "save-A")
    b = await replace_upload_default(database, scope, (1,), a.default.access_revision, "save-B")
    c = await replace_upload_default(database, scope, (2,), b.default.access_revision, "save-C")
    await change_group(
        database,
        scope.actor.access,
        scope.groups[lost],
        scope.actor.access.actor_principal_id,
        AccessGroupChangeKind.REMOVE_MANAGER,
        c.default.access_revision,
        "remove-actor-manager",
    )
    before = await upload_default_effects(database, scope.project_id)
    if lost == 0:
        recovered = await replace_upload_default(
            database, scope, (1,), a.default.access_revision, "save-B"
        )
        assert recovered.default == b.default
        assert not recovered.operation.created
        assert recovered.default.audience == UploadAudience((scope.groups[1].group_id,))
    else:
        with pytest.raises(AccessDeniedError):
            await replace_upload_default(database, scope, (1,), a.default.access_revision, "save-B")
    assert await upload_default_effects(database, scope.project_id) == before
    async with database.session() as session:
        original = await session.get(ProjectUploadDefaultResultRow, b.operation.operation_id.value)
        assert original is not None and original.before_group_ids == [
            scope.groups[0].group_id.value
        ]
        assert original.group_ids == [scope.groups[1].group_id.value]


async def test_reference_blocks_deletion_until_replacement_and_history_does_not_pin_old_groups(
    database: Database, scope: UploadDefaultScenario
) -> None:
    a = await replace_upload_default(database, scope, (0,), scope.revision, "save-A")
    with pytest.raises(ConflictError):
        await delete_group(database, scope.actor.access, scope.groups[0], a.default.access_revision)
    b = await replace_upload_default(database, scope, (1,), a.default.access_revision, "save-B")
    deleted = await delete_group(
        database, scope.actor.access, scope.groups[0], b.default.access_revision
    )
    assert deleted.group.group_id == scope.groups[0].group_id
    async with database.session() as session:
        assert (
            await session.get(ProjectUploadDefaultResultRow, a.operation.operation_id.value)
            is not None
        )
        assert (
            await session.get(ProjectUploadDefaultResultRow, b.operation.operation_id.value)
            is not None
        )
    effects = await upload_default_effects(database, scope.project_id)
    assert effects[0] == (scope.groups[1].group_id.value,)


@pytest.mark.parametrize("failure", ["audit", "original", "before-commit", "cancel"])
async def test_required_persistence_failure_rolls_back_all_effects(
    database: Database, scope: UploadDefaultScenario, failure: str
) -> None:
    before = await upload_default_effects(database, scope.project_id)
    async with database.session() as session:

        def reject_flush(current: Session, _context: object, _instances: object) -> None:
            if any(
                (
                    isinstance(row, AccessAuditEventRow)
                    and row.event_type == "project_upload_default_changed"
                )
                if failure == "audit"
                else isinstance(row, ProjectUploadDefaultResultRow)
                for row in current.new
            ):
                raise RuntimeError("Controlled required persistence failure")

        def reject_commit(_session: Session) -> None:
            if failure == "cancel":
                raise asyncio.CancelledError()
            raise RuntimeError("Controlled failure before COMMIT")

        hook = "before_flush" if failure in ("audit", "original") else "before_commit"
        callback = reject_flush if failure in ("audit", "original") else reject_commit
        event.listen(session.sync_session, hook, callback)
        try:
            with pytest.raises(
                asyncio.CancelledError if failure == "cancel" else RuntimeError,
                match=None if failure == "cancel" else "Controlled",
            ):
                await upload_default_service(session).set(
                    access=scope.actor.access,
                    command=_command(scope),
                    context=upload_default_context(scope.project_id),
                )
        finally:
            event.remove(session.sync_session, hook, callback)
    assert await upload_default_effects(database, scope.project_id) == before


async def test_failure_after_shared_completion_rolls_back_default_and_all_originals(
    database: Database, scope: UploadDefaultScenario
) -> None:
    class FailAfterCompletion(IdempotencyService):
        @override
        async def record_completed_result(
            self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
        ):
            await super().record_completed_result(operation, replay_kind=replay_kind)
            raise RuntimeError("Controlled failure after shared completion")

    before = await upload_default_effects(database, scope.project_id)
    async with database.session() as session:
        service = ProjectUploadDefaultService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            default_facts_reader=PostgresProjectUploadDefaultFactsReader(session),
            default_repository=PostgresProjectUploadDefaultRepository(session),
            operation_idempotency=FailAfterCompletion(PostgresOperationReservationWriter(session)),
            default_fingerprint_service=ProjectUploadDefaultFingerprintService(
                group_fingerprints()
            ),
        )
        with pytest.raises(RuntimeError, match="after shared completion"):
            await service.set(
                access=scope.actor.access,
                command=_command(scope),
                context=upload_default_context(scope.project_id),
            )
    assert await upload_default_effects(database, scope.project_id) == before


async def test_lost_application_ack_after_real_commit_recovers_without_reapplying(
    database: Database, scope: UploadDefaultScenario
) -> None:
    """Use the delivered application acknowledgment seam, not a physical DB wire fault."""
    async with database.session() as session:

        def lose_ack(_session: Session) -> None:
            raise RuntimeError("Controlled lost COMMIT acknowledgment")

        event.listen(session.sync_session, "after_commit", lose_ack)
        try:
            with pytest.raises(RuntimeError, match="lost COMMIT acknowledgment"):
                await upload_default_service(session).set(
                    access=scope.actor.access,
                    command=_command(scope),
                    context=upload_default_context(scope.project_id),
                )
        finally:
            event.remove(session.sync_session, "after_commit", lose_ack)
    committed = await upload_default_effects(database, scope.project_id)
    assert committed[1:] == (scope.revision + 1, 1, 1, 1)
    later = await replace_upload_default(database, scope, (1,), scope.revision + 1, "later")
    before = await upload_default_effects(database, scope.project_id)
    recovered = await replace_upload_default(database, scope, (0,), scope.revision)
    assert recovered.default.access_revision == scope.revision + 1
    assert recovered.default.audience != later.default.audience
    assert await upload_default_effects(database, scope.project_id) == before


async def _wait[T](
    database: Database, task: asyncio.Task[T], holder_pid: int, *, preceding_pid: int | None = None
) -> int:
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    blocking = func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains([holder_pid])
    if preceding_pid is not None:
        blocking = blocking | func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
            [preceding_pid]
        )
    async with asyncio.timeout(3):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        blocking,
                        pid != preceding_pid if preceding_pid is not None else pid.is_not(None),
                    )
                )
            if blocked is not None:
                return blocked
            await asyncio.sleep(0.01)
    await task
    pytest.fail("Default operation bypassed the required coordination wait.")


@pytest.mark.parametrize("loss", ["manager", "member"])
async def test_authority_is_refreshed_after_project_wait(
    database: Database, scope: UploadDefaultScenario, loss: str
) -> None:
    a = await replace_upload_default(database, scope, (0,), scope.revision, "save-A")
    appointed = await change_group(
        database,
        scope.actor.access,
        scope.groups[0],
        scope.bob_id,
        AccessGroupChangeKind.APPOINT_MANAGER,
        a.default.access_revision,
        "keep-manager",
    )
    task: asyncio.Task[ProjectUploadDefaultChangeResultDTO] | None = None
    work_error: BaseException | None = None
    observed_rejection: BaseException | None = None
    before = await upload_default_effects(database, scope.project_id)
    async with database.session() as holder:
        try:
            await holder.begin()
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            await holder.scalar(
                select(ProjectRow.id)
                .where(ProjectRow.id == scope.project_id.value)
                .with_for_update()
            )
            task = asyncio.create_task(
                replace_upload_default(
                    database, scope, (1,), appointed.access_revision, "after-wait"
                )
            )
            await _wait(database, task, holder_pid)
            await holder.execute(
                delete(GroupManagerRow).where(
                    GroupManagerRow.project_id == scope.project_id.value,
                    GroupManagerRow.group_id == scope.groups[0].group_id.value,
                    GroupManagerRow.principal_id == scope.actor.access.actor_principal_id.value,
                )
            )
            if loss == "member":
                await holder.execute(
                    delete(GroupMembershipRow).where(
                        GroupMembershipRow.project_id == scope.project_id.value,
                        GroupMembershipRow.group_id == scope.groups[0].group_id.value,
                        GroupMembershipRow.principal_id
                        == scope.actor.access.actor_principal_id.value,
                    )
                )
            await holder.execute(
                update(ProjectRow)
                .where(ProjectRow.id == scope.project_id.value)
                .values(access_revision=appointed.access_revision + 1)
            )
            async with asyncio.timeout(3):
                await holder.commit()
            with pytest.raises(AccessDeniedError) as denied:
                async with asyncio.timeout(3):
                    await task
            observed_rejection = denied.value
        except BaseException as error:
            work_error = error
            raise
        finally:
            cleanup_errors: list[BaseException] = []
            try:
                async with asyncio.timeout(3):
                    await holder.rollback()
            except BaseException as rollback_error:
                cleanup_errors.append(rollback_error)
            owned: list[asyncio.Task[ProjectUploadDefaultChangeResultDTO]] = (
                [task] if task is not None else []
            )
            try:
                async with asyncio.timeout(3):
                    for owned_task in owned:
                        if not owned_task.done():
                            owned_task.cancel()
                    outcomes = await asyncio.shield(asyncio.gather(*owned, return_exceptions=True))
                cleanup_errors.extend(
                    outcome
                    for outcome in outcomes
                    if isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not work_error
                    and outcome is not observed_rejection
                    and not any(outcome is error for error in cleanup_errors)
                )
            except BaseException as task_error:
                if not any(task_error is error for error in cleanup_errors):
                    cleanup_errors.append(task_error)
            if cleanup_errors:
                if work_error is not None and not any(
                    work_error is error for error in cleanup_errors
                ):
                    cleanup_errors.insert(0, work_error)
                raise BaseExceptionGroup(
                    "Holder rollback and task finalization failed", cleanup_errors
                ) from None
    after = await upload_default_effects(database, scope.project_id)
    assert after[0] == before[0] and after[2:] == before[2:]


async def test_expired_original_cannot_overwrite_later_saved_default(
    database: Database, scope: UploadDefaultScenario
) -> None:
    first = await replace_upload_default(database, scope, (0,), scope.revision)
    later = await replace_upload_default(
        database, scope, (1,), first.default.access_revision, "later"
    )
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == first.operation.operation_id.value)
            .values(
                expires_at=func.clock_timestamp(type_=DateTime(timezone=True))
                - timedelta(seconds=1)
            )
        )
    before = await upload_default_effects(database, scope.project_id)
    with pytest.raises(StaleRevisionError):
        await replace_upload_default(database, scope, (0,), scope.revision)
    assert await upload_default_effects(database, scope.project_id) == before
    assert later.default.access_revision == scope.revision + 2


async def test_revision_overflow_keeps_saved_default_and_history_intact(
    database: Database, scope: UploadDefaultScenario
) -> None:
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == scope.project_id.value)
            .values(access_revision=9007199254740991)
        )
    before = await upload_default_effects(database, scope.project_id)
    with pytest.raises(ConflictError):
        await replace_upload_default(database, scope, (0,), 9007199254740991)
    assert await upload_default_effects(database, scope.project_id) == before


@pytest.mark.parametrize("same_original", [False, True])
async def test_concurrent_updates_preserve_one_transition(
    database: Database, scope: UploadDefaultScenario, same_original: bool
) -> None:
    tasks = [
        asyncio.create_task(replace_upload_default(database, scope, (0,), scope.revision, "one")),
        asyncio.create_task(
            replace_upload_default(
                database,
                scope,
                (0,) if same_original else (1,),
                scope.revision,
                "one" if same_original else "two",
            )
        ),
    ]
    work_error: BaseException | None = None
    consumed: list[BaseException] = []
    try:
        async with asyncio.timeout(3):
            outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        accepted = [
            outcome
            for outcome in outcomes
            if isinstance(outcome, ProjectUploadDefaultChangeResultDTO)
        ]
        rejected = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        if same_original:
            assert len(accepted) == 2 and not rejected
            assert accepted[0].operation.operation_id == accepted[1].operation.operation_id
            assert sum(result.operation.created for result in accepted) == 1
        else:
            assert len(accepted) == len(rejected) == 1
            assert isinstance(rejected[0], StaleRevisionError)
            consumed.append(rejected[0])
        effects = await upload_default_effects(database, scope.project_id)
        assert effects[1:] == (scope.revision + 1, 1, 1, 1)
        assert accepted[0].default.audience is not None
        assert effects[0] == tuple(group.value for group in accepted[0].default.audience.group_ids)
    except BaseException as error:
        work_error = error
        raise
    finally:
        try:
            async with asyncio.timeout(3):
                for task in tasks:
                    if not task.done():
                        task.cancel()
                final = await asyncio.shield(asyncio.gather(*tasks, return_exceptions=True))
            errors = [
                outcome
                for outcome in final
                if isinstance(outcome, BaseException)
                and not isinstance(outcome, asyncio.CancelledError)
                and outcome is not work_error
                and not any(outcome is error for error in consumed)
            ]
            if errors:
                raise BaseExceptionGroup("Unconsumed concurrent default outcome", errors)
        except BaseException as cleanup_error:
            if work_error is not None and cleanup_error is not work_error:
                raise BaseExceptionGroup(
                    "Concurrent defaults and cleanup failed", [work_error, cleanup_error]
                ) from None
            raise


@pytest.mark.parametrize("winner", ["default", "deletion"])
async def test_group_deletion_and_default_update_take_the_same_project_turn(
    database: Database, scope: UploadDefaultScenario, winner: str
) -> None:
    async def request(
        kind: str,
    ) -> ProjectUploadDefaultChangeResultDTO | AccessGroupDeletionResultDTO:
        if kind == "default":
            return await replace_upload_default(
                database, scope, (0,), scope.revision, "racing-default"
            )
        return await delete_group(
            database, scope.actor.access, scope.groups[0], scope.revision, "racing-deletion"
        )

    tasks: list[
        asyncio.Task[ProjectUploadDefaultChangeResultDTO | AccessGroupDeletionResultDTO]
    ] = []
    work_error: BaseException | None = None
    observed_rejection: BaseException | None = None
    async with database.session() as holder:
        try:
            await holder.begin()
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            await holder.scalar(
                select(ProjectRow.id)
                .where(ProjectRow.id == scope.project_id.value)
                .with_for_update()
            )
            first = asyncio.create_task(request(winner))
            tasks.append(first)
            first_pid = await _wait(database, first, holder_pid)
            second = asyncio.create_task(request("deletion" if winner == "default" else "default"))
            tasks.append(second)
            await _wait(database, second, holder_pid, preceding_pid=first_pid)
            async with asyncio.timeout(3):
                await holder.commit()
            async with asyncio.timeout(3):
                result = await first
                assert isinstance(
                    result,
                    ProjectUploadDefaultChangeResultDTO
                    if winner == "default"
                    else AccessGroupDeletionResultDTO,
                )
                with pytest.raises(
                    StaleRevisionError if winner == "default" else ResourceNotFoundError
                ) as denied:
                    await second
                observed_rejection = denied.value
            effects = await upload_default_effects(database, scope.project_id)
            if winner == "default":
                assert effects == ((scope.groups[0].group_id.value,), scope.revision + 1, 1, 1, 1)
            else:
                assert effects == ((), scope.revision + 1, 0, 0, 0)
        except BaseException as error:
            work_error = error
            raise
        finally:
            cleanup_errors: list[BaseException] = []
            try:
                async with asyncio.timeout(3):
                    await holder.rollback()
            except BaseException as rollback_error:
                cleanup_errors.append(rollback_error)
            owned = tasks
            try:
                async with asyncio.timeout(3):
                    for owned_task in owned:
                        if not owned_task.done():
                            owned_task.cancel()
                    outcomes = await asyncio.shield(asyncio.gather(*owned, return_exceptions=True))
                cleanup_errors.extend(
                    outcome
                    for outcome in outcomes
                    if isinstance(outcome, BaseException)
                    and not isinstance(outcome, asyncio.CancelledError)
                    and outcome is not work_error
                    and outcome is not observed_rejection
                    and not any(outcome is error for error in cleanup_errors)
                )
            except BaseException as task_error:
                if not any(task_error is error for error in cleanup_errors):
                    cleanup_errors.append(task_error)
            if cleanup_errors:
                if work_error is not None and not any(
                    work_error is error for error in cleanup_errors
                ):
                    cleanup_errors.insert(0, work_error)
                raise BaseExceptionGroup(
                    "Holder rollback and task finalization failed", cleanup_errors
                ) from None
