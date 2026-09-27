"""Verify grant-change facts come from the exact current Access records."""

import os
from uuid import uuid4

import pytest
from sqlalchemy import update
from tests.support.access_scenarios import MockAccessScenarios

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
@pytest.mark.parametrize("can_grant", [False, True])
async def test_reads_exact_current_grant_level(
    database: Database,
    can_grant: bool,
) -> None:
    """Can-use authority must not appear as can-grant authority."""
    async with database.session() as session, session.begin():
        scenario = await MockAccessScenarios.seed_project_authorization(
            session,
            is_project_member=True,
            has_action_grant=True,
        )
        recipient_id = PrincipalId(uuid4())

        session.add(
            PrincipalRow(
                id=recipient_id.value,
                organization_id=scenario.organization_id.value,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.ACTIVE,
                display_name="Bob",
            )
        )
        await session.flush()

        session.add(
            ProjectMembershipRow(
                project_id=scenario.project_id.value,
                principal_id=recipient_id.value,
                organization_id=scenario.organization_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )

        # Fixture setup: make Alice's existing assignment delegable in one case.
        if can_grant:
            await session.execute(
                update(ProjectActionGrantRow)
                .where(
                    ProjectActionGrantRow.project_id == scenario.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == scenario.principal_id.value,
                    ProjectActionGrantRow.action == scenario.action.value,
                )
                .values(can_grant=True)
            )

    async with database.session() as session, session.begin():
        reader = PostgresProjectGrantChangeFactsReader(session)
        access = AccessContextDTO(actor_principal_id=scenario.principal_id)

        facts = await reader.read_for_change(
            access=access,
            project_id=scenario.project_id,
            recipient_principal_id=recipient_id,
            action_id=scenario.action,
        )
        other_action_facts = await reader.read_for_change(
            access=access,
            project_id=scenario.project_id,
            recipient_principal_id=recipient_id,
            action_id=ActionId("other-project-action"),
        )

    assert facts is not None
    assert facts.actor.id == scenario.principal_id
    assert facts.recipient is not None
    assert facts.recipient.id == recipient_id
    assert facts.project_status is ProjectStatus.ACTIVE
    assert facts.project_access_revision == 0
    assert facts.actor_is_project_member
    assert facts.recipient_is_project_member
    assert facts.actor_can_grant_action is can_grant

    assert other_action_facts is not None
    assert not other_action_facts.actor_can_grant_action
