"""Verify project-action authorization reads current facts from PostgreSQL."""

import os

import pytest
from access_test_support import seed_multi_project_authorization, seed_project_authorization

from inframeld_backend.access.application.access_authorizer import (
    AccessAuthorizer,
    AccessContext,
    ActionTarget,
)
from inframeld_backend.access.domain.authorization import ActionAuthorizationFacts
from inframeld_backend.access.infrastructure.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.shared.application.errors import AccessDeniedError, ResourceNotFoundError
from inframeld_backend.shared.infrastructure.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
)


@pytest.mark.asyncio
async def test_allows_member_with_exact_project_action_grant(database: Database) -> None:
    """Allow a current project member whose exact action grant is stored in PostgreSQL."""
    async with database.session() as session, session.begin():
        scenario = await seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )

        authorizer = AccessAuthorizer(PostgresProjectActionFactsReader(session))
        await authorizer.require_action(
            access=AccessContext(actor_principal_id=scenario.principal_id),
            action=scenario.action,
            target=ActionTarget(
                project_id=scenario.project_id,
                target_kind="project",
                target_id=scenario.project_id,
            ),
        )


@pytest.mark.asyncio
async def test_returns_hidden_facts_for_active_nonmember(database: Database) -> None:
    """Hide an existing project from an active principal who is not its member."""
    async with database.session() as session, session.begin():
        scenario = await seed_project_authorization(
            session,
            is_project_member=False,
            has_action_grant=False,
        )
        reader = PostgresProjectActionFactsReader(session)
        authorizer = AccessAuthorizer(reader)

        with pytest.raises(ResourceNotFoundError):
            await authorizer.require_action(
                access=AccessContext(actor_principal_id=scenario.principal_id),
                action=scenario.action,
                target=ActionTarget(
                    project_id=scenario.project_id,
                    target_kind="project",
                    target_id=scenario.project_id,
                ),
            )

        facts = await reader.read_action_facts(
            access=AccessContext(actor_principal_id=scenario.principal_id),
            action=scenario.action,
            target=ActionTarget(
                project_id=scenario.project_id,
                target_kind="project",
                target_id=scenario.project_id,
            ),
        )

    assert facts.authorization == ActionAuthorizationFacts(
        principal_is_active=True,
        is_project_member=False,
        has_exact_action_grant=False,
    )
    assert facts.target_is_visible is False


@pytest.mark.asyncio
async def test_denies_project_member_without_exact_action_grant(database: Database) -> None:
    """Deny a visible project member who lacks the requested action grant."""
    async with database.session() as session, session.begin():
        scenario = await seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=False,
        )
        authorizer = AccessAuthorizer(PostgresProjectActionFactsReader(session))

        with pytest.raises(AccessDeniedError):
            await authorizer.require_action(
                access=AccessContext(actor_principal_id=scenario.principal_id),
                action=scenario.action,
                target=ActionTarget(
                    project_id=scenario.project_id,
                    target_kind="project",
                    target_id=scenario.project_id,
                ),
            )


@pytest.mark.asyncio
async def test_hides_suspended_project_member_even_with_an_action_grant(
    database: Database,
) -> None:
    """Stop a suspended principal even when its old membership and grant remain stored."""
    async with database.session() as session, session.begin():
        scenario = await seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_status="suspended",
        )
        authorizer = AccessAuthorizer(PostgresProjectActionFactsReader(session))

        with pytest.raises(ResourceNotFoundError):
            await authorizer.require_action(
                access=AccessContext(actor_principal_id=scenario.principal_id),
                action=scenario.action,
                target=ActionTarget(
                    project_id=scenario.project_id,
                    target_kind="project",
                    target_id=scenario.project_id,
                ),
            )


@pytest.mark.asyncio
async def test_project_action_grant_does_not_carry_to_another_project(database: Database) -> None:
    """Keep Alice's exact action grant limited to the project where it was assigned."""
    async with database.session() as session, session.begin():
        scenario = await seed_multi_project_authorization(session)
        authorizer = AccessAuthorizer(PostgresProjectActionFactsReader(session))
        access = AccessContext(actor_principal_id=scenario.principal_id)

        await authorizer.require_action(
            access=access,
            action=scenario.action,
            target=ActionTarget(
                project_id=scenario.granted_project_id,
                target_kind="project",
                target_id=scenario.granted_project_id,
            ),
        )

        with pytest.raises(AccessDeniedError):
            await authorizer.require_action(
                access=access,
                action=scenario.action,
                target=ActionTarget(
                    project_id=scenario.ungranted_project_id,
                    target_kind="project",
                    target_id=scenario.ungranted_project_id,
                ),
            )


@pytest.mark.asyncio
async def test_allows_application_principal_with_its_exact_project_action_grant(
    database: Database,
) -> None:
    """Apply current project action checks to an application principal as well as a human."""
    async with database.session() as session, session.begin():
        scenario = await seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
            principal_kind="application",
        )
        authorizer = AccessAuthorizer(PostgresProjectActionFactsReader(session))

        await authorizer.require_action(
            access=AccessContext(actor_principal_id=scenario.principal_id),
            action=scenario.action,
            target=ActionTarget(
                project_id=scenario.project_id,
                target_kind="project",
                target_id=scenario.project_id,
            ),
        )
