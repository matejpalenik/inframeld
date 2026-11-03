"""Qualify stored membership reads, current authority and scoped continuation in PostgreSQL.

Creation is the delivered membership producer. Extra fixture relationships below
exercise read states without claiming an invitation or membership mutation API.
"""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, event, select, update
from sqlalchemy.orm import ORMExecuteState
from tests.support.access_scenarios import MockAccessScenarios
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.queries.list_project_members_query import (
    ListProjectMembersQuery,
)
from inframeld_backend.access.application.services.project_members_service import (
    ProjectMembersService,
)
from inframeld_backend.access.application.value_objects.project_members_cursor import (
    ProjectMembersCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.postgres_project_members_facts_reader import (
    PostgresProjectMembersFactsReader,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.project_members_composition import open_project_members
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def test_real_creation_produces_creator_read_with_use_only_authority_and_one_snapshot(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    created = await create_project(database, seed)
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectActionGrantRow)
            .where(ProjectActionGrantRow.action == "manage-project-members")
            .values(can_grant=False)
        )
        creator = await session.get(PrincipalRow, seed.access.actor_principal_id.value)
        assert creator is not None
        expected_name = creator.display_name
    observations: list[bool] = []

    def observed(execution: ORMExecuteState) -> None:
        observations.append(execution.is_select)

    async with database.session() as session:
        event.listen(session.sync_session, "do_orm_execute", observed)
        try:
            page = await ProjectMembersService(
                PostgresProjectMembersFactsReader(session)
            ).list_members(
                access=seed.access, query=ListProjectMembersQuery(created.project.project_id)
            )
        finally:
            event.remove(session.sync_session, "do_orm_execute", observed)
    assert observations == [True]
    assert page.project_id == created.project.project_id and page.access_revision == 1
    assert [(item.principal_id, item.display_name, item.kind) for item in page.items] == [
        (seed.access.actor_principal_id, expected_name, PrincipalKind.HUMAN)
    ]
    assert page.next_cursor is None
    async with database.session() as session:
        assert await session.scalar(select(OrganizationRow.access_revision)) == 1
        assert await session.scalar(select(ProjectRow.access_revision)) == 1


async def test_pages_include_stored_inactive_human_and_application_relationships_with_fresh_revision(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    created = await create_project(database, seed)
    project = created.project.project_id
    fixtures = [
        (UUID(int=10), PrincipalKind.HUMAN, PrincipalStatus.SUSPENDED),
        (UUID(int=20), PrincipalKind.APPLICATION, PrincipalStatus.RETIRED),
        (UUID(int=30), PrincipalKind.HUMAN, PrincipalStatus.ACTIVE),
    ]
    async with database.session() as session, session.begin():
        for principal_id, kind, status in fixtures:
            session.add(
                PrincipalRow(
                    id=principal_id,
                    organization_id=seed.organization_id.value,
                    kind=kind,
                    status=status,
                    display_name="Same legacy\nlabel",
                )
            )
        session.add(
            PrincipalRow(
                id=UUID(int=5),
                organization_id=seed.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Not a member",
            )
        )
        await session.flush()
        session.add(
            ApplicationAccountRow(
                principal_id=UUID(int=20),
                organization_id=seed.organization_id.value,
                project_id=project.value,
                principal_kind=PrincipalKind.APPLICATION,
            )
        )
        await session.flush()
        for principal_id, kind, _status in fixtures:
            session.add(
                ProjectMembershipRow(
                    project_id=project.value,
                    principal_id=principal_id,
                    organization_id=seed.organization_id.value,
                    principal_kind=kind,
                    application_principal_id=principal_id
                    if kind is PrincipalKind.APPLICATION
                    else None,
                )
            )
        await MockAccessScenarios.seed_project_authorization(
            session, is_project_member=True, has_action_grant=True
        )
    async with open_project_members(database) as reader:
        first = await reader.list_members(
            access=seed.access, query=ListProjectMembersQuery(project, 2)
        )
    assert [item.principal_id.value for item in first.items] == [UUID(int=10), UUID(int=20)]
    assert first.items[1].kind is PrincipalKind.APPLICATION and first.access_revision == 1
    assert first.next_cursor is not None
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectRow).where(ProjectRow.id == project.value).values(access_revision=2)
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == UUID(int=30))
            .values(display_name="Updated")
        )
    async with open_project_members(database) as reader:
        second = await reader.list_members(
            access=seed.access, query=ListProjectMembersQuery(project, 2, first.next_cursor)
        )
    assert second.access_revision == 2 and second.next_cursor is None
    assert [item.principal_id.value for item in second.items] == [
        UUID(int=30),
        seed.access.actor_principal_id.value,
    ]
    assert second.items[0].display_name == "Updated"
    assert first.items[0].display_name == "Same legacy\nlabel"


async def test_empty_continuation_retains_header_and_rechecks_authority(database: Database) -> None:
    seed = await seed_project_creator(database)
    created = await create_project(database, seed)
    project = created.project.project_id
    token = ProjectMembersCursor(
        seed.binding.installation_id,
        seed.organization_id,
        project,
        PrincipalId(UUID(int=(1 << 128) - 1)),
    ).to_token()
    async with open_project_members(database) as reader:
        empty = await reader.list_members(
            access=seed.access, query=ListProjectMembersQuery(project, cursor=token)
        )
    assert empty.project_id == project and empty.access_revision == 1
    assert empty.items == () and empty.next_cursor is None
    async with database.session() as session, session.begin():
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == project.value,
                ProjectActionGrantRow.action == "manage-project-members",
            )
        )
    with pytest.raises(AccessDeniedError):
        async with open_project_members(database) as reader:
            await reader.list_members(
                access=seed.access, query=ListProjectMembersQuery(project, cursor=token)
            )


async def test_cursor_from_another_project_cannot_be_used_as_empty_success(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    first = await create_project(database, seed)
    second = await create_project(database, seed, name="second", key="second")
    token = ProjectMembersCursor(
        seed.binding.installation_id,
        seed.organization_id,
        first.project.project_id,
        PrincipalId(UUID(int=(1 << 128) - 1)),
    ).to_token()
    with pytest.raises(InvalidInputError):
        async with open_project_members(database) as reader:
            await reader.list_members(
                access=seed.access,
                query=ListProjectMembersQuery(second.project.project_id, cursor=token),
            )


@pytest.mark.parametrize("case", ["grant", "membership", "suspended", "foreign-project"])
async def test_current_authority_and_visibility_apply_before_member_disclosure(
    database: Database, case: str
) -> None:
    seed = await seed_project_creator(database)
    created = await create_project(database, seed)
    project = created.project.project_id
    async with database.session() as session, session.begin():
        if case in {"grant", "membership"}:
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == project.value
                )
            )
            if case == "membership":
                await session.execute(
                    delete(ProjectMembershipRow).where(
                        ProjectMembershipRow.project_id == project.value
                    )
                )
        elif case == "suspended":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == seed.access.actor_principal_id.value)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        else:
            foreign = await MockAccessScenarios.seed_project_authorization(
                session, is_project_member=True, has_action_grant=True
            )
            project = foreign.project_id
    with pytest.raises(
        ResourceNotFoundError if case in {"membership", "foreign-project"} else AccessDeniedError
    ):
        async with open_project_members(database) as reader:
            await reader.list_members(access=seed.access, query=ListProjectMembersQuery(project))


@pytest.mark.parametrize("case", ["oauth", "recovery"])
async def test_current_credential_and_pending_recovery_block_stored_membership_read(
    database: Database, case: str
) -> None:
    seed = await seed_project_creator(database)
    created = await create_project(database, seed)
    access = seed.access
    async with database.session() as session, session.begin():
        if case == "oauth":
            access = AccessContextDTO(seed.access.actor_principal_id, seed.binding)
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id == seed.binding.installation_id.value,
                    HumanCredentialVersionRow.authority == seed.binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == seed.binding.identity.subject.value,
                )
                .values(version=seed.binding.version.value + 1)
            )
        else:
            session.add(
                IdentityRecoveryAdmissionRow(
                    operation_id="pending-members-recovery",
                    installation_id=seed.binding.installation_id.value,
                    authority=seed.binding.identity.authority.value,
                    flow_id=uuid4(),
                    subject=seed.binding.identity.subject.value,
                    event_kind=IdentityRecoveryEventKind.PASSWORD_RESET,
                )
            )
    with pytest.raises(HumanOAuthCredentialRejectedError if case == "oauth" else AccessDeniedError):
        async with open_project_members(database) as reader:
            await reader.list_members(
                access=access, query=ListProjectMembersQuery(created.project.project_id)
            )
