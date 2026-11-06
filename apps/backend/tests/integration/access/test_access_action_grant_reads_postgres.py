"""Qualify exact stored grants, eligible choices and existing own-access reads."""

import os
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select, update
from tests.support.access_group_scenarios import change_group, create_group
from tests.support.application_account_scenarios import create_account
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.project_action_grant_postgres_scenarios import change_project_grant
from tests.support.project_creation_scenarios import create_project
from tests.support.project_membership_postgres_scenarios import (
    MembershipProjectSeedDTO,
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.set_access_group_action_grant_command import (
    SetAccessGroupActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_organization_action_grant_command import (
    SetOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.application.dtos.created_application_account_dto import (
    CreatedApplicationAccountDTO,
)
from inframeld_backend.access.application.dtos.my_project_access_grant_dto import (
    MyProjectAccessGrantDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.queries.get_my_project_access_query import (
    GetMyProjectAccessQuery,
)
from inframeld_backend.access.application.queries.list_access_group_action_grants_query import (
    ListAccessGroupActionGrantsQuery,
)
from inframeld_backend.access.application.queries.list_application_account_action_grants_query import (
    ListApplicationAccountActionGrantsQuery,
)
from inframeld_backend.access.application.queries.list_organization_action_grants_query import (
    ListOrganizationActionGrantsQuery,
)
from inframeld_backend.access.application.queries.list_project_grant_recipients_query import (
    ListProjectGrantRecipientsQuery,
)
from inframeld_backend.access.application.value_objects.access_action_grants_cursor import (
    AccessActionGrantsCursor,
)
from inframeld_backend.access.application.value_objects.grant_recipients_cursor import (
    GrantRecipientsCursor,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.access_group_grant_composition import (
    open_access_group_grant_change,
    open_access_group_grant_read,
)
from inframeld_backend.bootstrap.application_account_grant_composition import (
    open_application_account_grant_change,
    open_application_account_grant_read,
)
from inframeld_backend.bootstrap.grant_recipients_composition import open_project_grant_recipients
from inframeld_backend.bootstrap.my_project_access_composition import open_my_project_access
from inframeld_backend.bootstrap.organization_access_composition import open_my_organization_access
from inframeld_backend.bootstrap.organization_grant_composition import (
    open_organization_grant_change,
    open_organization_grant_read,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL services",
    ),
]


@dataclass(frozen=True, slots=True)
class _ReadScope:
    seed: MembershipProjectSeedDTO
    group: CreatedAccessGroupDTO
    account: CreatedApplicationAccountDTO


def _fingerprints() -> RequestFingerprintService:
    return RequestFingerprintService(RequestFingerprintKey(b"K" * 32))


def _bob(scope: _ReadScope) -> AccessContextDTO:
    return AccessContextDTO(
        actor_principal_id=scope.seed.bob_id,
        authentication_evidence=MockAuthenticationEvidence.browser(
            VerifiedHumanIdentityDTO(
                authority=scope.seed.actor.binding.identity.authority,
                subject=IdentitySubject(str(UUID(int=200))),
            ),
        ),
    )


async def _scope(database: Database) -> _ReadScope:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="read-join-bob")
    group = (
        await create_group(database, seed.actor.access, seed.project.project_id, revision=2)
    ).group
    account = (
        await create_account(database, seed.actor.access, seed.project.project_id, revision=3)
    ).account
    return _ReadScope(seed=seed, group=group, account=account)


async def _project_revision(database: Database, scope: _ReadScope) -> int:
    async with database.session() as session:
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(
                ProjectRow.id == scope.seed.project.project_id.value
            )
        )
        assert revision is not None
        return revision


async def _organization_revision(database: Database, scope: _ReadScope) -> int:
    async with database.session() as session:
        revision = await session.scalar(
            select(OrganizationRow.access_revision).where(
                OrganizationRow.id == scope.seed.actor.organization_id.value
            )
        )
        assert revision is not None
        return revision


async def _group_grant(
    database: Database, scope: _ReadScope, *, recipient: PrincipalId, level: bool, key: str
) -> None:
    revision = await _project_revision(database, scope)
    async with open_access_group_grant_change(database, _fingerprints()) as service:
        await service.set_grant(
            access=scope.seed.actor.access,
            command=SetAccessGroupActionGrantCommand(
                project_id=scope.seed.project.project_id,
                group_id=scope.group.group_id,
                recipient_principal_id=recipient,
                action_id=ActionId("add-documents"),
                can_grant=level,
                expected_access_revision=revision,
            ),
            context=IdempotencyContextDTO(
                method=HttpMethod.PUT,
                requested_route=f"/v1/projects/{scope.seed.project.project_id.value}/access-groups/{scope.group.group_id.value}/grants/{recipient.value}/add-documents",
                key=IdempotencyKey(key),
            ),
        )


async def _account_grant(
    database: Database,
    scope: _ReadScope,
    *,
    recipient: PrincipalId,
    level: bool,
    key: str,
    access: AccessContextDTO | None = None,
) -> None:
    revision = await _project_revision(database, scope)
    async with open_application_account_grant_change(database, _fingerprints()) as service:
        await service.set_grant(
            access=access or scope.seed.actor.access,
            command=SetApplicationAccountActionGrantCommand(
                project_id=scope.seed.project.project_id,
                application_principal_id=scope.account.principal_id,
                recipient_principal_id=recipient,
                action_id=ActionId("issue-application-keys"),
                can_grant=level,
                expected_access_revision=revision,
            ),
            context=IdempotencyContextDTO(
                method=HttpMethod.PUT,
                requested_route=f"/v1/projects/{scope.seed.project.project_id.value}/application-accounts/{scope.account.principal_id.value}/grants/{recipient.value}/issue-application-keys",
                key=IdempotencyKey(key),
            ),
        )


async def _organization_grant(
    database: Database,
    scope: _ReadScope,
    *,
    recipient: PrincipalId,
    level: bool,
    key: str,
    access: AccessContextDTO | None = None,
) -> None:
    revision = await _organization_revision(database, scope)
    async with open_organization_grant_change(database, _fingerprints()) as service:
        await service.set_grant(
            access=access or scope.seed.actor.access,
            command=SetOrganizationActionGrantCommand(
                organization_id=scope.seed.actor.organization_id,
                recipient_principal_id=recipient,
                action_id=ActionId("create-projects"),
                can_grant=level,
                expected_access_revision=revision,
            ),
            context=IdempotencyContextDTO(
                method=HttpMethod.PUT,
                requested_route=f"/v1/organizations/{scope.seed.actor.organization_id.value}/grants/{recipient.value}/create-projects",
                key=IdempotencyKey(key),
            ),
        )


async def _bob_status(database: Database, scope: _ReadScope, status: PrincipalStatus) -> None:
    async with database.session() as session, session.begin():
        await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == scope.seed.actor.organization_id.value)
            .with_for_update()
        )
        await session.execute(
            update(PrincipalRow)
            .where(PrincipalRow.id == scope.seed.bob_id.value)
            .values(status=status)
        )
        await session.execute(
            update(OrganizationRow)
            .where(OrganizationRow.id == scope.seed.actor.organization_id.value)
            .values(access_revision=OrganizationRow.access_revision + 1)
        )


async def test_existing_organization_and_project_own_reads_report_actual_new_use_only_grants(
    database: Database,
) -> None:
    scope = await _scope(database)
    await _organization_grant(
        database, scope, recipient=scope.seed.bob_id, level=False, key="own-org-use"
    )
    await _group_grant(
        database, scope, recipient=scope.seed.bob_id, level=False, key="own-group-use"
    )
    await _account_grant(
        database, scope, recipient=scope.seed.bob_id, level=False, key="own-account-use"
    )
    revision = await _project_revision(database, scope)
    await change_project_grant(
        database,
        scope.seed,
        revision=revision,
        key="own-project-use",
        action_id=ActionId("inspect-budget"),
        can_grant=False,
    )
    async with open_my_organization_access(database) as reader:
        organization = await reader.read(access=_bob(scope))
    assert organization.principal_id == scope.seed.bob_id
    assert organization.organization_id == scope.seed.actor.organization_id
    assert organization.access_revision == await _organization_revision(database, scope)
    assert [(item.action_id.value, item.can_grant) for item in organization.grants] == [
        ("create-projects", False)
    ]
    async with open_my_project_access(database) as reader:
        project = await reader.get_access(
            access=_bob(scope),
            query=GetMyProjectAccessQuery(project_id=scope.seed.project.project_id, limit=100),
        )
    assert (
        project.principal_id == scope.seed.bob_id
        and project.project_id == scope.seed.project.project_id
    )
    assert project.access_revision == await _project_revision(database, scope)
    assert (
        project.group_memberships == ()
        and project.group_managements == ()
        and project.next_cursor is None
    )
    assert set(project.grants) == {
        MyProjectAccessGrantDTO(
            target=ProjectGrantTargetDTO(project_id=scope.seed.project.project_id),
            action_id=ActionId("inspect-budget"),
            can_grant=False,
        ),
        MyProjectAccessGrantDTO(
            target=AccessGroupGrantTargetDTO(
                project_id=scope.seed.project.project_id, access_group_id=scope.group.group_id
            ),
            action_id=ActionId("add-documents"),
            can_grant=False,
        ),
        MyProjectAccessGrantDTO(
            target=ApplicationAccountGrantTargetDTO(
                project_id=scope.seed.project.project_id,
                application_principal_id=scope.account.principal_id,
            ),
            action_id=ActionId("issue-application-keys"),
            can_grant=False,
        ),
    }


async def test_organization_stored_grants_page_keeps_suspended_rows_and_current_delegation(
    database: Database,
) -> None:
    scope = await _scope(database)
    await _organization_grant(
        database, scope, recipient=scope.seed.bob_id, level=False, key="read-org-bob"
    )
    await _bob_status(database, scope, PrincipalStatus.SUSPENDED)
    query = ListOrganizationActionGrantsQuery(
        organization_id=scope.seed.actor.organization_id,
        action_id=ActionId("create-projects"),
        limit=1,
    )
    async with open_organization_grant_read(database) as reader:
        first = await reader.list_grants(access=scope.seed.actor.access, query=query)
    assert len(first.items) == 1 and first.next_cursor is not None
    async with open_organization_grant_read(database) as reader:
        second = await reader.list_grants(
            access=scope.seed.actor.access, query=replace(query, cursor=first.next_cursor)
        )
    assert len(second.items) == 1 and second.next_cursor is None
    assert {item.recipient_principal_id: item.can_grant for item in first.items + second.items} == {
        scope.seed.actor.access.actor_principal_id: True,
        scope.seed.bob_id: False,
    }
    empty_cursor = replace(
        AccessActionGrantsCursor.from_token(first.next_cursor),
        after=second.items[-1].recipient_principal_id,
    ).to_token()
    async with open_organization_grant_read(database) as reader:
        empty = await reader.list_grants(
            access=scope.seed.actor.access, query=replace(query, cursor=empty_cursor)
        )
    assert empty.items == () and empty.next_cursor is None
    await _bob_status(database, scope, PrincipalStatus.ACTIVE)
    await _organization_grant(
        database, scope, recipient=scope.seed.bob_id, level=True, key="read-org-delegate-bob"
    )
    await _organization_grant(
        database,
        scope,
        recipient=scope.seed.actor.access.actor_principal_id,
        level=False,
        key="read-org-downgrade-alice",
        access=_bob(scope),
    )
    async with open_organization_grant_read(database) as reader:
        with pytest.raises(AccessDeniedError):
            await reader.list_grants(
                access=scope.seed.actor.access, query=replace(query, cursor=empty_cursor)
            )


async def test_group_stored_grants_page_uses_current_same_group_manager_and_empty_header(
    database: Database,
) -> None:
    scope = await _scope(database)
    await _group_grant(
        database, scope, recipient=scope.seed.bob_id, level=False, key="read-group-bob"
    )
    await _group_grant(
        database,
        scope,
        recipient=scope.seed.actor.access.actor_principal_id,
        level=True,
        key="read-group-alice",
    )
    await _bob_status(database, scope, PrincipalStatus.SUSPENDED)
    query = ListAccessGroupActionGrantsQuery(
        project_id=scope.seed.project.project_id,
        group_id=scope.group.group_id,
        action_id=ActionId("add-documents"),
        limit=1,
    )
    async with open_access_group_grant_read(database) as reader:
        first = await reader.list_grants(access=scope.seed.actor.access, query=query)
    assert len(first.items) == 1 and first.next_cursor is not None
    async with open_access_group_grant_read(database) as reader:
        second = await reader.list_grants(
            access=scope.seed.actor.access, query=replace(query, cursor=first.next_cursor)
        )
    assert len(second.items) == 1 and second.next_cursor is None
    assert {item.recipient_principal_id: item.can_grant for item in first.items + second.items} == {
        scope.seed.actor.access.actor_principal_id: True,
        scope.seed.bob_id: False,
    }
    empty_cursor = replace(
        AccessActionGrantsCursor.from_token(first.next_cursor),
        after=second.items[-1].recipient_principal_id,
    ).to_token()
    await _bob_status(database, scope, PrincipalStatus.ACTIVE)
    revision = await _project_revision(database, scope)
    await change_group(
        database,
        scope.seed.actor.access,
        scope.group,
        scope.seed.bob_id,
        AccessGroupChangeKind.APPOINT_MANAGER,
        revision,
        "read-appoint-bob",
    )
    await _group_grant(
        database,
        scope,
        recipient=scope.seed.actor.access.actor_principal_id,
        level=False,
        key="read-group-alice-use",
    )
    async with open_access_group_grant_read(database) as reader:
        empty = await reader.list_grants(
            access=scope.seed.actor.access, query=replace(query, cursor=empty_cursor)
        )
    assert empty.items == () and empty.next_cursor is None
    revision = await _project_revision(database, scope)
    await change_group(
        database,
        scope.seed.actor.access,
        scope.group,
        scope.seed.actor.access.actor_principal_id,
        AccessGroupChangeKind.REMOVE_MANAGER,
        revision,
        "read-demote-alice",
    )
    async with open_access_group_grant_read(database) as reader:
        with pytest.raises(AccessDeniedError):
            await reader.list_grants(
                access=scope.seed.actor.access, query=replace(query, cursor=empty_cursor)
            )


async def test_application_stored_grants_page_keeps_levels_and_rechecks_exact_delegation(
    database: Database,
) -> None:
    scope = await _scope(database)
    await _account_grant(
        database, scope, recipient=scope.seed.bob_id, level=False, key="read-account-bob"
    )
    await _bob_status(database, scope, PrincipalStatus.SUSPENDED)
    query = ListApplicationAccountActionGrantsQuery(
        project_id=scope.seed.project.project_id,
        application_principal_id=scope.account.principal_id,
        action_id=ActionId("issue-application-keys"),
        limit=1,
    )
    async with open_application_account_grant_read(database) as reader:
        first = await reader.list_grants(access=scope.seed.actor.access, query=query)
    assert len(first.items) == 1 and first.next_cursor is not None
    async with open_application_account_grant_read(database) as reader:
        second = await reader.list_grants(
            access=scope.seed.actor.access, query=replace(query, cursor=first.next_cursor)
        )
    assert len(second.items) == 1 and second.next_cursor is None
    assert {item.recipient_principal_id: item.can_grant for item in first.items + second.items} == {
        scope.seed.actor.access.actor_principal_id: True,
        scope.seed.bob_id: False,
    }
    empty_cursor = replace(
        AccessActionGrantsCursor.from_token(first.next_cursor),
        after=second.items[-1].recipient_principal_id,
    ).to_token()
    async with open_application_account_grant_read(database) as reader:
        empty = await reader.list_grants(
            access=scope.seed.actor.access, query=replace(query, cursor=empty_cursor)
        )
    assert empty.items == () and empty.next_cursor is None
    await _bob_status(database, scope, PrincipalStatus.ACTIVE)
    await _account_grant(
        database, scope, recipient=scope.seed.bob_id, level=True, key="read-account-delegate-bob"
    )
    await _account_grant(
        database,
        scope,
        recipient=scope.seed.actor.access.actor_principal_id,
        level=False,
        key="read-account-alice-use",
        access=_bob(scope),
    )
    async with open_application_account_grant_read(database) as reader:
        with pytest.raises(AccessDeniedError):
            await reader.list_grants(
                access=scope.seed.actor.access, query=replace(query, cursor=empty_cursor)
            )


async def _seed_directory_choices(database: Database, scope: _ReadScope) -> PrincipalId:
    """Put recovery/version exclusions before a recovered eligible choice in UUID order."""
    organization = scope.seed.actor.organization_id.value
    installation = scope.seed.actor.binding.installation_id.value
    authority = scope.seed.actor.binding.identity.authority.value
    async with database.session() as session, session.begin():
        for value in range(1, 6):
            session.add(
                PrincipalRow(
                    id=UUID(int=value),
                    organization_id=organization,
                    kind=PrincipalKind.HUMAN,
                    status=PrincipalStatus.SUSPENDED if value == 1 else PrincipalStatus.ACTIVE,
                    display_name="Recovered choice" if value == 5 else "Not an eligible choice",
                )
            )
        await session.flush()
        for value in range(1, 6):
            session.add(
                ProjectMembershipRow(
                    project_id=scope.seed.project.project_id.value,
                    principal_id=UUID(int=value),
                    organization_id=organization,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )
        # 3 is pending, 4 has released history without a version, and 5 has both.
        for value in (3, 4, 5):
            subject = str(UUID(int=3000 + value))
            session.add(
                HumanIdentityLinkRow(
                    authority=authority,
                    subject=subject,
                    organization_id=organization,
                    principal_id=UUID(int=value),
                    principal_kind=PrincipalKind.HUMAN,
                )
            )
            if value != 4:
                session.add(
                    HumanCredentialVersionRow(
                        installation_id=installation,
                        authority=authority,
                        subject=subject,
                        version=2,
                    )
                )
            admission = IdentityRecoveryAdmissionRow(
                operation_id=str(UUID(int=5000 + value)),
                installation_id=installation,
                authority=authority,
                flow_id=UUID(int=4000 + value),
                subject=subject,
                event_kind=IdentityRecoveryEventKind.RECOVERY,
            )
            if value != 3:
                admission.kratos_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
                admission.hydra_cleanup_state = IdentityRecoveryCleanupState.CONFIRMED
                admission.released_at = datetime.now(UTC)
            session.add(admission)
    return PrincipalId(UUID(int=5))


@pytest.mark.parametrize("kind", ["project", "access-group", "application-account"])
async def test_recipient_directory_filters_before_limit_for_actual_scoped_target_variants(
    database: Database, kind: str
) -> None:
    scope = await _scope(database)
    recovered_choice = await _seed_directory_choices(database, scope)
    async with open_my_organization_access(database) as own:
        reviewed = await own.read(access=scope.seed.actor.access)
    other = (
        await create_project(
            database,
            replace(scope.seed.actor, access_revision=reviewed.access_revision),
            name="directory-other",
            key="directory-other-project",
        )
    ).project
    foreign_account = (
        await create_account(
            database,
            scope.seed.actor.access,
            other.project_id,
            revision=1,
            name="foreign-bot",
            key="directory-foreign-bot",
        )
    ).account
    foreign_group = (
        await create_group(
            database,
            scope.seed.actor.access,
            other.project_id,
            revision=2,
            name="foreign-group",
            key="directory-foreign-group",
        )
    ).group
    target: ProjectGrantTargetDTO | AccessGroupGrantTargetDTO | ApplicationAccountGrantTargetDTO
    if kind == "project":
        target, action = (
            ProjectGrantTargetDTO(project_id=scope.seed.project.project_id),
            ActionId("inspect-budget"),
        )
    elif kind == "access-group":
        target, action = (
            AccessGroupGrantTargetDTO(
                project_id=scope.seed.project.project_id, access_group_id=scope.group.group_id
            ),
            ActionId("add-documents"),
        )
    else:
        target, action = (
            ApplicationAccountGrantTargetDTO(
                project_id=scope.seed.project.project_id,
                application_principal_id=scope.account.principal_id,
            ),
            ActionId("issue-application-keys"),
        )
    query = ListProjectGrantRecipientsQuery(
        project_id=scope.seed.project.project_id, target=target, action_id=action, limit=1
    )
    expected = {scope.seed.actor.access.actor_principal_id, scope.seed.bob_id, recovered_choice}
    if kind != "application-account":
        expected.add(scope.account.principal_id)
    found: list[PrincipalId] = []
    for _ in range(len(expected) + 1):
        async with open_project_grant_recipients(database) as reader:
            page = await reader.list_recipients(access=scope.seed.actor.access, query=query)
        assert len(page.items) == 1
        found.append(page.items[0].principal_id)
        assert page.items[0].principal_id in expected
        assert page.items[0].kind in {PrincipalKind.HUMAN, PrincipalKind.APPLICATION}
        if page.next_cursor is None:
            break
        query = replace(query, cursor=page.next_cursor)
    assert found == sorted(expected, key=lambda principal: principal.value.int)
    assert foreign_account.principal_id not in found
    assert query.cursor is not None
    after_last = replace(GrantRecipientsCursor.from_token(query.cursor), after=found[-1]).to_token()
    async with open_project_grant_recipients(database) as reader:
        empty = await reader.list_recipients(
            access=scope.seed.actor.access, query=replace(query, cursor=after_last)
        )
    assert empty.items == () and empty.next_cursor is None
    if kind == "project":
        revision = await _project_revision(database, scope)
        await change_project_grant(
            database,
            scope.seed,
            revision=revision,
            key="directory-project-delegate-bob",
            action_id=ActionId("inspect-budget"),
            can_grant=True,
        )
        await change_project_grant(
            database,
            scope.seed,
            revision=revision + 1,
            key="directory-project-alice-use",
            action_id=ActionId("inspect-budget"),
            recipient=scope.seed.actor.access.actor_principal_id,
            can_grant=False,
            access=_bob(scope),
        )
    elif kind == "access-group":
        revision = await _project_revision(database, scope)
        await change_group(
            database,
            scope.seed.actor.access,
            scope.group,
            scope.seed.bob_id,
            AccessGroupChangeKind.APPOINT_MANAGER,
            revision,
            "directory-appoint-bob",
        )
        await change_group(
            database,
            scope.seed.actor.access,
            scope.group,
            scope.seed.actor.access.actor_principal_id,
            AccessGroupChangeKind.REMOVE_MANAGER,
            revision + 1,
            "directory-demote-alice",
        )
    else:
        await _account_grant(
            database,
            scope,
            recipient=scope.seed.bob_id,
            level=True,
            key="directory-account-delegate-bob",
        )
        await _account_grant(
            database,
            scope,
            recipient=scope.seed.actor.access.actor_principal_id,
            level=False,
            key="directory-account-alice-use",
            access=_bob(scope),
        )
    async with open_project_grant_recipients(database) as reader:
        with pytest.raises(AccessDeniedError):
            await reader.list_recipients(
                access=scope.seed.actor.access, query=replace(query, cursor=after_last)
            )
    for wrong, wrong_action in [
        (
            AccessGroupGrantTargetDTO(
                project_id=scope.seed.project.project_id, access_group_id=foreign_group.group_id
            ),
            ActionId("add-documents"),
        ),
        (
            ApplicationAccountGrantTargetDTO(
                project_id=scope.seed.project.project_id,
                application_principal_id=foreign_account.principal_id,
            ),
            ActionId("issue-application-keys"),
        ),
    ]:
        async with open_project_grant_recipients(database) as reader:
            with pytest.raises(ResourceNotFoundError):
                await reader.list_recipients(
                    access=scope.seed.actor.access,
                    query=ListProjectGrantRecipientsQuery(
                        project_id=scope.seed.project.project_id,
                        target=wrong,
                        action_id=wrong_action,
                    ),
                )
