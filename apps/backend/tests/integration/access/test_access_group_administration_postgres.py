"""Qualify real group relationships and scoped persistence in PostgreSQL."""

import asyncio
import os
from dataclasses import replace
from uuid import UUID

import pytest
from sqlalchemy import Integer, String, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.exc import IntegrityError
from tests.support.access_group_scenarios import (
    change_group,
    create_group,
    delete_group,
    group_command,
    group_context,
    group_creation_service,
)
from tests.support.application_account_scenarios import create_account
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_creation_scenarios import create_project, seed_project_creator
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.application.dtos.deleted_access_group_dto import DeletedAccessGroupDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.enums.access_group_collection import AccessGroupCollection
from inframeld_backend.access.application.queries.list_access_group_principals_query import (
    ListAccessGroupPrincipalsQuery,
)
from inframeld_backend.access.application.value_objects.access_group_principals_cursor import (
    AccessGroupPrincipalsCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.access_group_deletion_result_row import (
    AccessGroupDeletionResultRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_name_reservation_row import (
    AccessGroupNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_access_group_deletion_writer import (
    PostgresAccessGroupDeletionWriter,
)
from inframeld_backend.bootstrap.access_group_composition import open_access_group_read
from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_creation_atomically_seeds_creator_member_and_manager_without_document_grants(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    async with database.session() as session:
        created = await group_creation_service(session).create(
            access=seed.access,
            command=group_command(project.project_id),
            context=group_context(project.project_id),
        )
    group = created.group
    async with database.session() as session:
        stored = await session.get(AccessGroupRow, group.group_id.value)
        assert stored is not None and stored.name == "SupportKnowledge"
        identity = (
            project.project_id.value,
            group.group_id.value,
            seed.access.actor_principal_id.value,
        )
        assert await session.get(GroupMembershipRow, identity) is not None
        assert await session.get(GroupManagerRow, identity) is not None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupActionGrantRow)
                .where(GroupActionGrantRow.group_id == group.group_id.value)
            )
            == 0
        )
        assert group.access_revision == 2


async def _seed_group(database: Database) -> tuple[MembershipProjectSeedDTO, CreatedAccessGroupDTO]:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join-bob")
    return seed, (await create_group(database, seed.actor.access, seed.project.project_id, 2)).group


def _bob_access(seed: MembershipProjectSeedDTO) -> AccessContextDTO:
    return AccessContextDTO(
        seed.bob_id,
        MockAuthenticationEvidence.browser(
            VerifiedHumanIdentityDTO(
                seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
            )
        ),
    )


async def test_exact_name_collision_rolls_back_and_names_are_project_scoped(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    first = await create_group(database, seed.access, project.project_id)
    with pytest.raises(ConflictError):
        await create_group(database, seed.access, project.project_id, 2, key="same-name-new-key")
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(AccessGroupRow)) == 1
        assert (
            await session.scalar(select(func.count()).select_from(AccessGroupNameReservationRow))
            == 1
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == 2
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key == "same-name-new-key")
            )
            == 0
        )
    async with database.session() as session:
        organization_revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == seed.organization_id.value
            )
        )
        assert organization_revision is not None
    second_project = (
        await create_project(
            database,
            replace(seed, access_revision=organization_revision),
            name="other-project",
            key="create-other-project",
        )
    ).project
    second = await create_group(
        database, seed.access, second_project.project_id, key="same-name-other-project"
    )
    assert second.group.name == first.group.name and second.group.group_id != first.group.group_id


async def test_relationship_lifecycle_preserves_original_receipts_and_never_restores_management(
    database: Database,
) -> None:
    seed, group = await _seed_group(database)
    appointed = await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.APPOINT_MANAGER,
        3,
        "appoint-bob",
    )
    assert (
        appointed.relationships == AccessGroupRelationships(True, True)
        and appointed.status_code == 201
    )
    noop = await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.ADD_MEMBER,
        4,
        "already-member",
    )
    assert not noop.changed and noop.access_revision == 4 and noop.status_code == 200
    demoted = await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.REMOVE_MANAGER,
        4,
        "demote-bob",
    )
    assert demoted.relationships == AccessGroupRelationships(True, False)
    removed = await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.REMOVE_MEMBER,
        5,
        "remove-bob",
    )
    assert removed.relationships == AccessGroupRelationships(False, False)
    replay = await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.APPOINT_MANAGER,
        3,
        "appoint-bob",
    )
    assert replay.operation == replace(appointed.operation, created=False)
    assert replace(replay, operation=appointed.operation) == appointed
    joined = await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.ADD_MEMBER,
        6,
        "rejoin-bob",
    )
    assert joined.relationships == AccessGroupRelationships(True, False)
    removed_replay = await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.REMOVE_MEMBER,
        5,
        "remove-bob",
    )
    assert removed_replay.operation == replace(removed.operation, created=False)
    assert replace(removed_replay, operation=removed.operation) == removed
    async with database.session() as session:
        identity = (group.project_id.value, group.group_id.value, seed.bob_id.value)
        assert await session.get(GroupMembershipRow, identity) is not None
        assert await session.get(GroupManagerRow, identity) is None
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupActionGrantRow)
                .where(GroupActionGrantRow.group_id == group.group_id.value)
            )
            == 0
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 7


async def test_application_account_can_join_but_never_become_a_manager(database: Database) -> None:
    seed, group = await _seed_group(database)
    app = (await create_account(database, seed.actor.access, group.project_id, 3)).account
    added = await change_group(
        database,
        seed.actor.access,
        group,
        app.principal_id,
        AccessGroupChangeKind.ADD_MEMBER,
        4,
        "join-app",
    )
    assert added.relationships == AccessGroupRelationships(True, False)
    for kind in (AccessGroupChangeKind.APPOINT_MANAGER, AccessGroupChangeKind.REMOVE_MANAGER):
        with pytest.raises(InvalidInputError):
            await change_group(
                database,
                seed.actor.access,
                group,
                app.principal_id,
                kind,
                5,
                "manager-app-" + kind.value,
            )
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupActionGrantRow)
                .where(GroupActionGrantRow.recipient_principal_id == app.principal_id.value)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ProjectActionGrantRow)
                .where(ProjectActionGrantRow.recipient_principal_id == app.principal_id.value)
            )
            == 0
        )
        assert await session.scalar(select(func.count()).select_from(ApplicationKeyRow)) == 0


async def test_group_metadata_visibility_does_not_grant_management_or_page_inventory(
    database: Database,
) -> None:
    seed, group = await _seed_group(database)
    bob = _bob_access(seed)
    async with open_access_group_read(database) as reader:
        with pytest.raises(ResourceNotFoundError):
            await reader.inspect(access=bob, project_id=group.project_id, selector=group.group_id)
    async with database.session() as session, session.begin():
        session.add(
            GroupActionGrantRow(
                project_id=group.project_id.value,
                group_id=group.group_id.value,
                recipient_principal_id=seed.bob_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action="update-documents",
                can_grant=False,
                assigned_by_principal_id=seed.actor.access.actor_principal_id.value,
            )
        )
    async with open_access_group_read(database) as reader:
        assert (
            await reader.inspect(access=bob, project_id=group.project_id, selector=group.name)
        ).group_id == group.group_id
        with pytest.raises(AccessDeniedError):
            await reader.list_principals(
                access=bob,
                query=ListAccessGroupPrincipalsQuery(
                    group.project_id, group.group_id, AccessGroupCollection.MEMBERS
                ),
            )
    with pytest.raises(AccessDeniedError):
        await change_group(
            database,
            bob,
            group,
            seed.bob_id,
            AccessGroupChangeKind.ADD_MEMBER,
            3,
            "self-join-no-manager",
        )


async def test_unsupported_stored_group_action_does_not_reveal_id_or_exact_name_metadata(
    database: Database,
) -> None:
    seed, group = await _seed_group(database)
    bob = _bob_access(seed)
    async with database.session() as session, session.begin():
        session.add(
            GroupActionGrantRow(
                project_id=group.project_id.value,
                group_id=group.group_id.value,
                recipient_principal_id=seed.bob_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action="update-documents",
                can_grant=False,
                assigned_by_principal_id=seed.actor.access.actor_principal_id.value,
            )
        )
    for selector in (group.group_id, group.name):
        async with open_access_group_read(database) as reader:
            assert (
                await reader.inspect(access=bob, project_id=group.project_id, selector=selector)
            ).group_id == group.group_id

    async with database.session() as session, session.begin():
        await session.execute(
            update(GroupActionGrantRow)
            .where(
                GroupActionGrantRow.project_id == group.project_id.value,
                GroupActionGrantRow.group_id == group.group_id.value,
                GroupActionGrantRow.recipient_principal_id == seed.bob_id.value,
            )
            .values(action="unsupported-stored-action")
        )
    for selector in (group.group_id, group.name):
        async with open_access_group_read(database) as reader:
            with pytest.raises(ResourceNotFoundError):
                await reader.inspect(access=bob, project_id=group.project_id, selector=selector)


async def test_member_removal_removes_management_and_replay_requires_current_manager(
    database: Database,
) -> None:
    seed, group = await _seed_group(database)
    await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.APPOINT_MANAGER,
        3,
        "appoint-bob",
    )
    bob = _bob_access(seed)
    added = await change_group(
        database, bob, group, seed.bob_id, AccessGroupChangeKind.ADD_MEMBER, 4, "bob-noop"
    )
    assert not added.changed
    await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.REMOVE_MEMBER,
        4,
        "remove-manager-member",
    )
    with pytest.raises(AccessDeniedError):
        await change_group(
            database, bob, group, seed.bob_id, AccessGroupChangeKind.ADD_MEMBER, 4, "bob-noop"
        )
    async with database.session() as session:
        assert (
            await session.get(
                GroupManagerRow, (group.project_id.value, group.group_id.value, seed.bob_id.value)
            )
            is None
        )


@pytest.mark.parametrize("unusable", ["suspended", "application"])
async def test_last_manager_does_not_rely_on_an_ineligible_replacement(
    database: Database, unusable: str
) -> None:
    seed, group = await _seed_group(database)
    if unusable == "suspended":
        await change_group(
            database,
            seed.actor.access,
            group,
            seed.bob_id,
            AccessGroupChangeKind.APPOINT_MANAGER,
            3,
            "appoint-bob",
        )
        async with database.session() as session, session.begin():
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.bob_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        revision = 4
    else:
        app = (await create_account(database, seed.actor.access, group.project_id, 3)).account
        await change_group(
            database,
            seed.actor.access,
            group,
            app.principal_id,
            AccessGroupChangeKind.ADD_MEMBER,
            4,
            "join-app",
        )
        revision = 5
    with pytest.raises(ConflictError):
        await change_group(
            database,
            seed.actor.access,
            group,
            seed.actor.access.actor_principal_id,
            AccessGroupChangeKind.REMOVE_MANAGER,
            revision,
            "last-manager",
        )
    async with database.session() as session:
        assert (
            await session.get(
                GroupManagerRow,
                (
                    group.project_id.value,
                    group.group_id.value,
                    seed.actor.access.actor_principal_id.value,
                ),
            )
            is not None
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == revision


async def test_two_manager_departures_serialize_and_fresh_retry_keeps_the_last_manager(
    database: Database,
) -> None:
    seed, group = await _seed_group(database)
    await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.APPOINT_MANAGER,
        3,
        "appoint-bob",
    )
    alice, bob = seed.actor.access, _bob_access(seed)
    results = await asyncio.gather(
        change_group(
            database,
            alice,
            group,
            alice.actor_principal_id,
            AccessGroupChangeKind.REMOVE_MANAGER,
            4,
            "leave-alice",
        ),
        change_group(
            database,
            bob,
            group,
            bob.actor_principal_id,
            AccessGroupChangeKind.REMOVE_MANAGER,
            4,
            "leave-bob",
        ),
        return_exceptions=True,
    )
    assert sum(not isinstance(value, BaseException) for value in results) == 1
    assert any(isinstance(value, StaleRevisionError) for value in results)
    remaining = bob if isinstance(results[1], BaseException) else alice
    with pytest.raises(ConflictError):
        await change_group(
            database,
            remaining,
            group,
            remaining.actor_principal_id,
            AccessGroupChangeKind.REMOVE_MANAGER,
            5,
            "leave-last-fresh",
        )
    async with database.session() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(GroupManagerRow)
                .where(GroupManagerRow.group_id == group.group_id.value)
            )
            == 1
        )


async def test_member_pages_recheck_management_and_exact_cursor_scope(database: Database) -> None:
    seed, group = await _seed_group(database)
    await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.APPOINT_MANAGER,
        3,
        "appoint-bob",
    )
    async with open_access_group_read(database) as reader:
        page = await reader.list_principals(
            access=seed.actor.access,
            query=ListAccessGroupPrincipalsQuery(
                group.project_id, group.group_id, AccessGroupCollection.MEMBERS, 1
            ),
        )
    assert len(page.items) == 1 and page.next_cursor is not None
    cursor = AccessGroupPrincipalsCursor.from_token(page.next_cursor)
    assert cursor.after == page.items[0].principal_id
    async with open_access_group_read(database) as reader:
        rest = await reader.list_principals(
            access=seed.actor.access,
            query=ListAccessGroupPrincipalsQuery(
                group.project_id,
                group.group_id,
                AccessGroupCollection.MEMBERS,
                100,
                page.next_cursor,
            ),
        )
        assert len(rest.items) == 1 and rest.next_cursor is None
        assert rest.items[0].principal_id.value > page.items[0].principal_id.value
        with pytest.raises(InvalidInputError):
            await reader.list_principals(
                access=seed.actor.access,
                query=ListAccessGroupPrincipalsQuery(
                    group.project_id,
                    group.group_id,
                    AccessGroupCollection.MANAGERS,
                    1,
                    page.next_cursor,
                ),
            )
    await change_group(
        database,
        seed.actor.access,
        group,
        seed.bob_id,
        AccessGroupChangeKind.REMOVE_MANAGER,
        4,
        "demote-bob",
    )
    async with open_access_group_read(database) as reader:
        with pytest.raises(AccessDeniedError):
            await reader.list_principals(
                access=_bob_access(seed),
                query=ListAccessGroupPrincipalsQuery(
                    group.project_id,
                    group.group_id,
                    AccessGroupCollection.MEMBERS,
                    1,
                    page.next_cursor,
                ),
            )


async def test_deletion_retires_name_and_creation_replay_does_not_recreate_group(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    created = await create_group(database, seed.access, project.project_id)
    group = created.group
    async with database.session() as session, session.begin():
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(
                    delete(AccessGroupRow).where(AccessGroupRow.id == group.group_id.value)
                )
    removed = await delete_group(database, seed.access, group, 2)
    assert removed.group.access_revision == 3
    original = await create_group(database, seed.access, project.project_id)
    assert (
        original.group == created.group
        and original.operation.operation_id == created.operation.operation_id
    )
    with pytest.raises(ConflictError):
        await create_group(database, seed.access, project.project_id, 3, key="reuse-retired-name")
    async with open_access_group_read(database) as reader:
        with pytest.raises(ResourceNotFoundError):
            await reader.inspect(
                access=seed.access, project_id=group.project_id, selector=group.name
            )
    with pytest.raises(ResourceNotFoundError):
        await delete_group(database, seed.access, group, 2)
    async with database.session() as session:
        assert await session.get(AccessGroupRow, group.group_id.value) is None
        reserved = await session.get(
            AccessGroupNameReservationRow, (group.project_id.value, group.name.value)
        )
        assert reserved is not None and reserved.retired
        for relation in (GroupManagerRow, GroupMembershipRow, GroupActionGrantRow):
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(relation)
                    .where(relation.group_id == group.group_id.value)
                )
                == 0
            )
        assert await session.scalar(select(ProjectRow.access_revision)) == 3


async def test_failure_after_real_deletion_rolls_back_binding_name_relationships_revision_and_result(
    database: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed, group = await _seed_group(database)
    original = PostgresAccessGroupDeletionWriter.delete

    async def fail_after_delete(
        self: PostgresAccessGroupDeletionWriter,
        *,
        group: DeletedAccessGroupDTO,
        expected_project_revision: int,
        binding: DeletionStatusBindingDTO,
    ) -> None:
        await original(
            self, group=group, expected_project_revision=expected_project_revision, binding=binding
        )
        raise RuntimeError("Controlled failure after actual deletion effects.")

    with monkeypatch.context() as patch:
        patch.setattr(PostgresAccessGroupDeletionWriter, "delete", fail_after_delete)
        with pytest.raises(RuntimeError):
            await delete_group(database, seed.actor.access, group, 3)
    async with database.session() as session:
        assert await session.get(AccessGroupRow, group.group_id.value) is not None
        assert (
            await session.get(
                GroupManagerRow,
                (
                    group.project_id.value,
                    group.group_id.value,
                    seed.actor.access.actor_principal_id.value,
                ),
            )
            is not None
        )
        reserved = await session.get(
            AccessGroupNameReservationRow, (group.project_id.value, group.name.value)
        )
        assert reserved is not None and not reserved.retired
        for relation in (
            AccessGroupDeletionResultRow,
            DeletionStatusBindingRow,
            DeletionStatusObservationRow,
        ):
            assert await session.scalar(select(func.count()).select_from(relation)) == 0
        assert await session.scalar(select(ProjectRow.access_revision)) == 3
    assert (await delete_group(database, seed.actor.access, group, 3)).group.access_revision == 4


async def _wait_for_group_lock(
    database: Database, task: asyncio.Task[AccessGroupRelationshipResultDTO], holder_pid: int
) -> None:
    pid, name = column("pid", Integer), column("datname", String)
    activity = table("pg_stat_activity", pid, name)
    async with asyncio.timeout(10):
        while not task.done():
            async with database.session() as observer:
                blocked = await observer.scalar(
                    select(pid)
                    .select_from(activity)
                    .where(
                        name == func.current_database(type_=String()),
                        func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains([holder_pid]),
                    )
                )
            if blocked is not None:
                return
            await asyncio.sleep(0.01)
    task.result()
    pytest.fail("Group change bypassed the required Organization turn.")


@pytest.mark.parametrize(
    "cancel", [False, True], ids=["committed-suspension", "actual-cancellation"]
)
async def test_group_add_waits_for_organization_turn_and_never_uses_pre_wait_eligibility(
    database: Database, cancel: bool
) -> None:
    seed, group = await _seed_group(database)
    task: asyncio.Task[AccessGroupRelationshipResultDTO] | None = None
    try:
        async with database.session() as holder, holder.begin():
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            await holder.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == seed.actor.organization_id.value)
                .with_for_update()
            )
            task = asyncio.create_task(
                change_group(
                    database,
                    seed.actor.access,
                    group,
                    seed.bob_id,
                    AccessGroupChangeKind.ADD_MEMBER,
                    3,
                    "blocked-group-add",
                )
            )
            await _wait_for_group_lock(database, task, holder_pid)
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                await holder.execute(
                    update(PrincipalRow)
                    .where(PrincipalRow.id == seed.bob_id.value)
                    .values(status=PrincipalStatus.SUSPENDED)
                )
        if not cancel:
            with pytest.raises(ConflictError):
                await task
    finally:
        if task is not None:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    async with database.session() as session:
        assert (
            await session.get(
                GroupMembershipRow,
                (group.project_id.value, group.group_id.value, seed.bob_id.value),
            )
            is None
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 3
        assert (
            await session.scalar(
                select(func.count())
                .select_from(IdempotencyReservationRow)
                .where(IdempotencyReservationRow.request_key == "blocked-group-add")
            )
            == 0
        )


async def test_real_application_binding_cannot_join_a_group_in_another_project(
    database: Database,
) -> None:
    seed, group = await _seed_group(database)
    account = (await create_account(database, seed.actor.access, group.project_id, 3)).account
    async with database.session() as session:
        organization_revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == seed.actor.organization_id.value
            )
        )
        assert organization_revision is not None
    other_project = (
        await create_project(
            database,
            replace(seed.actor, access_revision=organization_revision),
            name="other-project",
            key="create-other-project",
        )
    ).project
    other_group = (
        await create_group(
            database, seed.actor.access, other_project.project_id, 1, key="other-group"
        )
    ).group
    with pytest.raises(ConflictError):
        await change_group(
            database,
            seed.actor.access,
            other_group,
            account.principal_id,
            AccessGroupChangeKind.ADD_MEMBER,
            2,
            "cross-project-app",
        )
    async with database.session() as session, session.begin():
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    GroupMembershipRow(
                        project_id=other_group.project_id.value,
                        group_id=other_group.group_id.value,
                        principal_id=account.principal_id.value,
                    )
                )
                await session.flush()
    await change_group(
        database,
        seed.actor.access,
        group,
        account.principal_id,
        AccessGroupChangeKind.ADD_MEMBER,
        4,
        "same-project-app",
    )
    async with database.session() as session, session.begin():
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    GroupManagerRow(
                        project_id=group.project_id.value,
                        group_id=group.group_id.value,
                        principal_id=account.principal_id.value,
                        principal_kind=PrincipalKind.APPLICATION,
                    )
                )
                await session.flush()
