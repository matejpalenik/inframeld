"""Verify project-action authorization reads current facts from PostgreSQL."""

import os
from uuid import uuid4

import pytest
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.services.action_authorization_service import (
    ActionAuthorizationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
)


@pytest.mark.asyncio
async def test_allows_member_with_exact_project_action_grant(database: Database) -> None:
    """Allow a current project member whose exact action grant is stored in PostgreSQL."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )

        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))
        authorized_organization_id = await authorizer.require_action(
            access=AccessContextDTO(actor_principal_id=scenario.principal_id),
            action_id=scenario.action,
            target=ProjectActionTargetDTO(
                project_id=scenario.project_id,
            ),
        )

    assert authorized_organization_id == scenario.organization_id


@pytest.mark.asyncio
async def test_hides_project_from_active_nonmember(database: Database) -> None:
    """Hide an existing project from an active principal who is not its member."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=False,
            has_action_grant=False,
        )
        reader = PostgresProjectActionFactsReader(session)
        authorizer = ActionAuthorizationService(reader)
        access = AccessContextDTO(actor_principal_id=scenario.principal_id)
        target = ProjectActionTargetDTO(project_id=scenario.project_id)

        with pytest.raises(ResourceNotFoundError):
            await authorizer.require_action(
                access=access,
                action_id=scenario.action,
                target=target,
            )

        facts = await reader.read_action_facts(
            access=access,
            action_id=scenario.action,
            target=target,
        )

    assert facts == ProjectActionFactsDTO(
        organization_id=scenario.organization_id,
        principal_status=PrincipalStatus.ACTIVE,
        project_status=ProjectStatus.ACTIVE,
        is_project_member=False,
        has_exact_action_grant=False,
    )


@pytest.mark.asyncio
async def test_denies_project_member_without_exact_action_grant(database: Database) -> None:
    """Deny a visible project member who lacks the requested action grant."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))

        with pytest.raises(AccessDeniedError):
            await authorizer.require_action(
                access=AccessContextDTO(actor_principal_id=scenario.principal_id),
                action_id=scenario.action,
                target=ProjectActionTargetDTO(
                    project_id=scenario.project_id,
                ),
            )


@pytest.mark.asyncio
async def test_hides_suspended_project_member_even_with_an_action_grant(
    database: Database,
) -> None:
    """Stop a suspended principal even when its old membership and grant remain stored."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_status=PrincipalStatus.SUSPENDED,
        )
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))

        with pytest.raises(ResourceNotFoundError):
            await authorizer.require_action(
                access=AccessContextDTO(actor_principal_id=scenario.principal_id),
                action_id=scenario.action,
                target=ProjectActionTargetDTO(
                    project_id=scenario.project_id,
                ),
            )


@pytest.mark.asyncio
async def test_project_action_grant_does_not_carry_to_another_project(database: Database) -> None:
    """Keep Alice's exact action grant limited to the project where it was assigned."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_multi_project_authorization(session)
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))
        access = AccessContextDTO(actor_principal_id=scenario.principal_id)

        await authorizer.require_action(
            access=access,
            action_id=scenario.action,
            target=ProjectActionTargetDTO(
                project_id=scenario.granted_project_id,
            ),
        )

        with pytest.raises(AccessDeniedError):
            await authorizer.require_action(
                access=access,
                action_id=scenario.action,
                target=ProjectActionTargetDTO(
                    project_id=scenario.ungranted_project_id,
                ),
            )


@pytest.mark.asyncio
async def test_allows_application_principal_with_its_exact_project_action_grant(
    database: Database,
) -> None:
    """Apply current project action checks to an application principal as well as a human."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_kind=PrincipalKind.APPLICATION,
        )
        authorizer = ActionAuthorizationService(PostgresProjectActionFactsReader(session))

        await authorizer.require_action(
            access=AccessContextDTO(actor_principal_id=scenario.principal_id),
            action_id=scenario.action,
            target=ProjectActionTargetDTO(
                project_id=scenario.project_id,
            ),
        )


@pytest.mark.asyncio
async def test_missing_project_returns_no_facts_and_is_hidden(database: Database) -> None:
    """Keep an absent project on the same not-found path as other hidden targets."""
    async with database.session() as session, session.begin():
        caller = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
        reader = PostgresProjectActionFactsReader(session)
        access = AccessContextDTO(caller.principal_id)
        target = ProjectActionTargetDTO(ProjectId(uuid4()))

        facts = await reader.read_action_facts(
            access=access,
            action_id=caller.action,
            target=target,
        )

        assert facts is None

        with pytest.raises(ResourceNotFoundError):
            await ActionAuthorizationService(reader).require_action(
                access=access,
                action_id=caller.action,
                target=target,
            )


@pytest.mark.asyncio
async def test_another_organizations_project_is_hidden(database: Database) -> None:
    """Keep organization scoping in SQL even when both projects and grants exist."""
    async with database.session() as session, session.begin():
        caller = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
        foreign = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
        reader = PostgresProjectActionFactsReader(session)
        access = AccessContextDTO(caller.principal_id)
        target = ProjectActionTargetDTO(foreign.project_id)

        facts = await reader.read_action_facts(
            access=access,
            action_id=caller.action,
            target=target,
        )

        assert facts is None

        with pytest.raises(ResourceNotFoundError):
            await ActionAuthorizationService(reader).require_action(
                access=access,
                action_id=caller.action,
                target=target,
            )
