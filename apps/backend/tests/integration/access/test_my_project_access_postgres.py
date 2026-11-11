"""Discover reviewed Access revisions through one current combined own-access page."""

import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, event, update
from sqlalchemy.orm import ORMExecuteState
from tests.support.project_action_grant_postgres_scenarios import seed_project_grant_recipients

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.my_project_access_page_dto import (
    MyProjectAccessPageDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.my_project_access_item_kind import (
    MyProjectAccessItemKind,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.queries.get_my_project_access_query import (
    GetMyProjectAccessQuery,
)
from inframeld_backend.access.application.services.my_project_access_service import (
    MyProjectAccessService,
)
from inframeld_backend.access.application.value_objects.my_project_access_cursor import (
    MyProjectAccessCursor,
)
from inframeld_backend.access.application.value_objects.my_project_access_position import (
    MyProjectAccessPosition,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_my_project_access_facts_reader import (
    PostgresMyProjectAccessFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
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


async def _read(
    database: Database,
    access: AccessContextDTO,
    project: ProjectId,
    *,
    limit: int = 25,
    cursor: str | None = None,
) -> MyProjectAccessPageDTO:
    async with database.session() as session:
        return await MyProjectAccessService(PostgresMyProjectAccessFactsReader(session)).get_access(
            access=access, query=GetMyProjectAccessQuery(project, limit, cursor)
        )


async def test_member_with_no_grants_can_discover_revision_in_one_empty_snapshot(
    database: Database,
) -> None:
    seed = await seed_project_grant_recipients(database)
    statements: list[bool] = []

    def observe(state: ORMExecuteState) -> None:
        statements.append(state.is_select)

    async with database.session() as session:
        event.listen(session.sync_session, "do_orm_execute", observe)
        try:
            page = await MyProjectAccessService(
                PostgresMyProjectAccessFactsReader(session)
            ).get_access(
                access=seed.bob_access,
                query=GetMyProjectAccessQuery(seed.project.project_id),
            )
        finally:
            event.remove(session.sync_session, "do_orm_execute", observe)
    assert statements == [True]
    assert (page.principal_id, page.access_revision) == (seed.bob_id, 2)
    assert (page.grants, page.group_memberships, page.group_managements, page.next_cursor) == (
        (),
        (),
        (),
        None,
    )


async def test_combined_page_covers_actual_project_group_and_application_targets_without_implicit_grants(
    database: Database,
) -> None:
    """Group/account rows are read-state fixtures, not invented public provisioning."""
    seed = await seed_project_grant_recipients(database)
    project, actor = seed.project.project_id.value, seed.actor.access.actor_principal_id.value
    group, application = UUID(int=310), UUID(int=311)
    async with database.session() as session, session.begin():
        session.add_all(
            [
                AccessGroupRow(id=group, project_id=project, name="Support documents"),
                PrincipalRow(
                    id=application,
                    organization_id=seed.actor.organization_id.value,
                    kind=PrincipalKind.APPLICATION,
                    status=PrincipalStatus.ACTIVE,
                    display_name="SupportBot",
                ),
            ]
        )
        await session.flush()
        session.add(
            ApplicationAccountRow(
                principal_id=application,
                organization_id=seed.actor.organization_id.value,
                project_id=project,
                principal_kind=PrincipalKind.APPLICATION,
            )
        )
        await session.flush()
        session.add_all(
            [
                GroupActionGrantRow(
                    project_id=project,
                    group_id=group,
                    recipient_principal_id=actor,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="edit-documents",
                    can_grant=False,
                ),
                ApplicationActionGrantRow(
                    project_id=project,
                    application_principal_id=application,
                    recipient_principal_id=actor,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="issue-application-keys",
                    can_grant=True,
                ),
                GroupMembershipRow(project_id=project, group_id=group, principal_id=actor),
            ]
        )
        await session.flush()
        session.add(
            GroupManagerRow(
                project_id=project,
                group_id=group,
                principal_id=actor,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
    cursor = None
    pages: list[MyProjectAccessPageDTO] = []
    async with asyncio.timeout(5):
        while True:
            page = await _read(
                database, seed.actor.access, seed.project.project_id, limit=1, cursor=cursor
            )
            assert len(page.grants) + len(page.group_memberships) + len(page.group_managements) == 1
            pages.append(page)
            cursor = page.next_cursor
            if cursor is None:
                break
    grants = tuple(grant for page in pages for grant in page.grants)
    assert len(grants) == 20 and len(pages) == 22
    assert sum(grant.action_id.value == "edit-documents" for grant in grants) == 1
    assert not any(grant.action_id.value == "view-documents" for grant in grants)
    assert tuple(group_id.value for page in pages for group_id in page.group_memberships) == (
        group,
    )
    assert tuple(group_id.value for page in pages for group_id in page.group_managements) == (
        group,
    )
    assert all(page.access_revision == 2 and page.principal_id.value == actor for page in pages)


@pytest.mark.parametrize("case", ["membership", "suspended", "oauth", "recovery"])
async def test_empty_continuation_still_observes_current_member_credential_and_recovery(
    database: Database, case: str
) -> None:
    seed = await seed_project_grant_recipients(database)
    cursor = MyProjectAccessCursor(
        seed.actor.binding.installation_id,
        seed.actor.organization_id,
        seed.project.project_id,
        seed.actor.access.actor_principal_id,
        MyProjectAccessPosition(MyProjectAccessItemKind.MANAGEMENT, UUID(int=2**128 - 1), None),
    ).to_token()
    assert (
        await _read(database, seed.actor.access, seed.project.project_id, cursor=cursor)
    ).next_cursor is None
    access = seed.actor.access
    actor = access.actor_principal_id.value
    async with database.session() as session, session.begin():
        if case == "membership":
            await session.execute(
                delete(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.recipient_principal_id == actor
                )
            )
            await session.execute(
                delete(ProjectMembershipRow).where(ProjectMembershipRow.principal_id == actor)
            )
        elif case == "suspended":
            await session.execute(
                update(PrincipalRow)
                .where(PrincipalRow.id == actor)
                .values(status=PrincipalStatus.SUSPENDED)
            )
        elif case == "oauth":
            access = AccessContextDTO(seed.actor.access.actor_principal_id, seed.actor.binding)
            await session.execute(
                update(HumanCredentialVersionRow)
                .where(
                    HumanCredentialVersionRow.installation_id
                    == seed.actor.binding.installation_id.value,
                    HumanCredentialVersionRow.authority
                    == seed.actor.binding.identity.authority.value,
                    HumanCredentialVersionRow.subject == seed.actor.binding.identity.subject.value,
                )
                .values(version=seed.actor.binding.version.value + 1)
            )
        else:
            session.add(
                IdentityRecoveryAdmissionRow(
                    operation_id="own-access-recovery",
                    installation_id=seed.actor.binding.installation_id.value,
                    authority=seed.actor.binding.identity.authority.value,
                    subject=seed.actor.binding.identity.subject.value,
                    flow_id=uuid4(),
                    event_kind=IdentityRecoveryEventKind.PASSWORD_RESET,
                )
            )
    error = (
        ResourceNotFoundError
        if case == "membership"
        else HumanOAuthCredentialRejectedError
        if case == "oauth"
        else AccessDeniedError
    )
    with pytest.raises(error):
        await _read(database, access, seed.project.project_id, cursor=cursor)


async def test_cursor_is_bound_to_the_current_principal(database: Database) -> None:
    seed = await seed_project_grant_recipients(database)
    page = await _read(database, seed.actor.access, seed.project.project_id, limit=1)
    assert page.next_cursor is not None
    with pytest.raises(InvalidInputError):
        await _read(
            database,
            seed.bob_access,
            seed.project.project_id,
            cursor=page.next_cursor,
        )
