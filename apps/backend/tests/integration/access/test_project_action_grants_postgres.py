"""Read exact stored assignments through real creation, admission and grant producers.

Typed inactive/application rows are read-state fixtures, not delivered account
provisioning or grant-administration APIs.
"""

import os
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import httpx2
import pytest
from pydantic import HttpUrl
from sqlalchemy import delete, event, func, select, update
from sqlalchemy.orm import ORMExecuteState
from tests.support.project_creation_scenarios import create_project, seed_project_creator
from tests.support.project_grant_changes import create_project_grant_change_service
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grants_page_dto import (
    ProjectActionGrantsPageDTO,
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
from inframeld_backend.access.application.queries.list_project_action_grants_query import (
    ListProjectActionGrantsQuery,
)
from inframeld_backend.access.application.services.project_action_grants_service import (
    ProjectActionGrantsService,
)
from inframeld_backend.access.application.value_objects.project_action_grants_cursor import (
    ProjectActionGrantsCursor,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_grants_facts_reader import (
    PostgresProjectActionGrantsFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
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
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.access.infrastructure.verifiers.kratos_human_identity_verifier import (
    KratosHumanIdentityVerifier,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]
ACTION = ActionId("inspect-budget")


async def test_registered_http_admission_membership_legacy_post_and_exact_grant_get(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    actor = await seed_project_creator(database)
    bob_identity = VerifiedHumanIdentityDTO(
        actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
    )
    browser = AsyncMock(return_value=actor.binding.identity)
    settings = get_settings().model_copy(
        update={
            "database": temporary_postgres_settings,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://kratos.test"),
                admin_url=HttpUrl("http://kratos-admin.test"),
                authority=actor.binding.identity.authority,
            ),
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
        }
    )
    with (
        patch.object(KratosBrowserSessionVerifier, "verify", browser),
        patch.object(KratosHumanIdentityVerifier, "verify", AsyncMock(return_value=bob_identity)),
    ):
        application = create_app(settings)
        async with (
            application.router.lifespan_context(application),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=application),
                base_url="https://api.test",
                headers={"Origin": "https://account.test", "X-Inframeld-CSRF": "1"},
                cookies={"ory_kratos_session": "controlled-alice"},
            ) as client,
        ):
            admission = await client.post(
                f"/v1/organizations/{actor.organization_id.value}/human-admissions",
                json={"identityId": str(UUID(int=200)), "expectedAccessRevision": 1},
                headers={"Idempotency-Key": "admit-bob"},
            )
            assert admission.status_code == 201
            bob = admission.json()["principalId"]
            creation = await client.post(
                "/v1/projects",
                json={
                    "organizationId": str(actor.organization_id.value),
                    "expectedAccessRevision": admission.json()["accessRevision"],
                    "name": "support",
                    "displayName": "Support",
                },
                headers={"Idempotency-Key": "create-support"},
            )
            assert creation.status_code == 201
            project = creation.json()["projectId"]
            joined = await client.put(
                f"/v1/projects/{project}/members/{bob}",
                json={"expectedAccessRevision": 1},
                headers={"Idempotency-Key": "join-bob"},
            )
            assert joined.status_code == 201
            granted = await client.post(
                f"/v1/projects/{project}/grants",
                json={
                    "recipientPrincipalId": bob,
                    "actionId": "create-access-groups",
                    "expectedAccessRevision": joined.json()["accessRevision"],
                },
                headers={"Idempotency-Key": "grant-bob"},
            )
            assert granted.status_code == 201
            del client.headers["X-Inframeld-CSRF"]
            del client.headers["Origin"]
            response = await client.get(
                f"/v1/projects/{project}/grants", params={"actionId": "create-access-groups"}
            )
            assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
            assert response.json() == {
                "items": [
                    {
                        "projectId": project,
                        "recipientPrincipalId": str(principal),
                        "actionId": "create-access-groups",
                        "canGrant": can_grant,
                    }
                    for principal, can_grant in sorted(
                        [(actor.access.actor_principal_id.value, True), (UUID(bob), False)]
                    )
                ],
                "nextCursor": None,
            }
            browser.return_value = bob_identity
            denied = await client.get(
                f"/v1/projects/{project}/grants", params={"actionId": "create-access-groups"}
            )
            assert denied.status_code == 403 and denied.json()["code"] == "access_denied"
            assert denied.headers["cache-control"] == "no-store"


async def _read(
    database: Database,
    access: AccessContextDTO,
    project: ProjectId,
    *,
    action: ActionId = ACTION,
    limit: int = 25,
    cursor: str | None = None,
) -> ProjectActionGrantsPageDTO:
    async with database.session() as session:
        return await ProjectActionGrantsService(
            PostgresProjectActionGrantsFactsReader(session)
        ).list_grants(
            access=access, query=ListProjectActionGrantsQuery(project, action, limit, cursor)
        )


async def test_real_creator_assignment_uses_one_select_and_changes_no_history(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project.project_id
    async with database.session() as session:
        before_audit = await session.scalar(select(func.count()).select_from(AccessAuditEventRow))
        before_reservations = await session.scalar(
            select(func.count()).select_from(IdempotencyReservationRow)
        )
    observations: list[bool] = []

    def observed(execution: ORMExecuteState) -> None:
        observations.append(execution.is_select)

    async with database.session() as session:
        event.listen(session.sync_session, "do_orm_execute", observed)
        try:
            page = await ProjectActionGrantsService(
                PostgresProjectActionGrantsFactsReader(session)
            ).list_grants(access=seed.access, query=ListProjectActionGrantsQuery(project, ACTION))
        finally:
            event.remove(session.sync_session, "do_orm_execute", observed)
    assert observations == [True]
    assert [
        (item.recipient_principal_id, item.action_id, item.can_grant) for item in page.items
    ] == [(seed.access.actor_principal_id, ACTION, True)]
    assert page.next_cursor is None
    async with database.session() as session:
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.value)
            )
            == 1
        )
        assert (
            await session.scalar(select(func.count()).select_from(AccessAuditEventRow))
            == before_audit
        )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyReservationRow))
            == before_reservations
        )


async def test_delivered_admission_membership_and_use_only_grant_are_readable(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join-bob")
    project = seed.project.project_id
    action = ActionId("create-access-groups")
    async with database.session() as session:
        await create_project_grant_change_service(session).assign_use_only(
            access=seed.actor.access,
            command=AssignProjectUseOnlyGrantCommand(project, seed.bob_id, action, 2),
            context=OperationAdmissionContextDTO(
                "POST", "/v1/projects/{project_id}/grants", IdempotencyKey("grant-bob")
            ),
        )
    page = await _read(database, seed.actor.access, project, action=action)
    assert {(item.recipient_principal_id, item.can_grant) for item in page.items} == {
        (seed.actor.access.actor_principal_id, True),
        (seed.bob_id, False),
    }


async def test_page_is_exact_project_action_and_retains_inactive_application_assignments(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project.project_id
    other = (
        await create_project(database, seed, name="other", key="other-project")
    ).project.project_id
    async with database.session() as session, session.begin():
        for principal_id, kind, status in [
            (UUID(int=10), PrincipalKind.HUMAN, PrincipalStatus.SUSPENDED),
            (UUID(int=20), PrincipalKind.APPLICATION, PrincipalStatus.RETIRED),
        ]:
            session.add(
                PrincipalRow(
                    id=principal_id,
                    organization_id=seed.organization_id.value,
                    kind=kind,
                    status=status,
                    display_name="private label",
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
        for principal_id, kind in [
            (UUID(int=10), PrincipalKind.HUMAN),
            (UUID(int=20), PrincipalKind.APPLICATION),
        ]:
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
        await session.flush()
        for principal_id, kind in [
            (UUID(int=10), PrincipalKind.HUMAN),
            (UUID(int=20), PrincipalKind.APPLICATION),
        ]:
            session.add(
                ProjectActionGrantRow(
                    project_id=project.value,
                    recipient_principal_id=principal_id,
                    recipient_kind=kind,
                    action=ACTION.value,
                    can_grant=False,
                )
            )
        session.add(
            ProjectActionGrantRow(
                project_id=project.value,
                recipient_principal_id=UUID(int=10),
                recipient_kind=PrincipalKind.HUMAN,
                action="inspect-feedback",
                can_grant=False,
            )
        )
    first = await _read(database, seed.access, project, limit=2)
    assert [item.recipient_principal_id.value for item in first.items] == [
        UUID(int=10),
        UUID(int=20),
    ]
    assert all(item.action_id == ACTION and not item.can_grant for item in first.items)
    assert first.next_cursor is not None
    second = await _read(database, seed.access, project, limit=2, cursor=first.next_cursor)
    assert [item.recipient_principal_id for item in second.items] == [
        seed.access.actor_principal_id
    ]
    assert second.next_cursor is None
    other_page = await _read(database, seed.access, other)
    assert [item.recipient_principal_id for item in other_page.items] == [
        seed.access.actor_principal_id
    ]


@pytest.mark.parametrize(
    "case", ["use-only", "grant", "membership", "suspended", "oauth", "recovery"]
)
async def test_continuation_rechecks_current_authority_even_when_page_is_empty(
    database: Database, case: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project.project_id
    cursor = ProjectActionGrantsCursor(
        seed.binding.installation_id,
        seed.organization_id,
        project,
        ACTION,
        PrincipalId(UUID(int=(1 << 128) - 1)),
    ).to_token()
    empty = await _read(database, seed.access, project, cursor=cursor)
    assert empty.items == () and empty.next_cursor is None
    access = seed.access
    async with database.session() as session, session.begin():
        exact = (
            ProjectActionGrantRow.project_id == project.value,
            ProjectActionGrantRow.recipient_principal_id == seed.access.actor_principal_id.value,
            ProjectActionGrantRow.action == ACTION.value,
        )
        if case == "use-only":
            await session.execute(
                update(ProjectActionGrantRow).where(*exact).values(can_grant=False)
            )
        elif case in {"grant", "membership"}:
            await session.execute(delete(ProjectActionGrantRow).where(*exact))
            if case == "membership":
                await session.execute(
                    delete(ProjectActionGrantRow).where(
                        ProjectActionGrantRow.project_id == project.value
                    )
                )
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
        elif case == "oauth":
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
                    operation_id="pending-grants-recovery",
                    installation_id=seed.binding.installation_id.value,
                    authority=seed.binding.identity.authority.value,
                    flow_id=uuid4(),
                    subject=seed.binding.identity.subject.value,
                    event_kind=IdentityRecoveryEventKind.PASSWORD_RESET,
                )
            )
    expected = (
        ResourceNotFoundError
        if case == "membership"
        else HumanOAuthCredentialRejectedError
        if case == "oauth"
        else AccessDeniedError
    )
    with pytest.raises(expected):
        await _read(database, access, project, cursor=cursor)


@pytest.mark.parametrize("case", ["project", "action"])
async def test_cursor_cannot_cross_project_or_action(database: Database, case: str) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project.project_id
    other = (
        (await create_project(database, seed, name="other", key="other-project")).project.project_id
        if case == "project"
        else project
    )
    cursor = ProjectActionGrantsCursor(
        seed.binding.installation_id,
        seed.organization_id,
        other,
        ActionId("inspect-feedback") if case == "action" else ACTION,
        PrincipalId(UUID(int=10)),
    ).to_token()
    with pytest.raises(InvalidInputError):
        await _read(database, seed.access, project, cursor=cursor)
