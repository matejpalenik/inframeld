"""Count only real current human responsibility, without providing grant/group workflows."""

import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_admission_writer import (
    PostgresIdentityRecoveryAdmissionWriter,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
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


@pytest.mark.parametrize("candidate", ["eligible", "suspended", "recovery", "missing-identity"])
async def test_only_eligible_coherent_human_can_preserve_an_exact_action(
    database: Database, candidate: str
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    carol = uuid4()
    identity = VerifiedHumanIdentityDTO(
        seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=201)))
    )
    project, organization = seed.project.project_id.value, seed.actor.organization_id.value
    async with database.session() as session, session.begin():
        session.add(
            PrincipalRow(
                id=carol,
                organization_id=organization,
                kind=PrincipalKind.HUMAN,
                status=PrincipalStatus.SUSPENDED
                if candidate == "suspended"
                else PrincipalStatus.ACTIVE,
                display_name="Carol",
            )
        )
        await session.flush()
        if candidate != "missing-identity":
            session.add(
                HumanIdentityLinkRow(
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    organization_id=organization,
                    principal_id=carol,
                    principal_kind=PrincipalKind.HUMAN,
                )
            )
            session.add(
                HumanCredentialVersionRow(
                    installation_id=seed.actor.binding.installation_id.value,
                    authority=identity.authority.value,
                    subject=identity.subject.value,
                    version=1,
                )
            )
        session.add(
            ProjectMembershipRow(
                project_id=project,
                organization_id=organization,
                principal_id=carol,
                principal_kind=PrincipalKind.HUMAN,
            )
        )
        await session.flush()
        for principal in (carol, seed.bob_id.value):
            session.add(
                ProjectActionGrantRow(
                    project_id=project,
                    recipient_principal_id=principal,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="create-access-groups",
                    can_grant=True,
                )
            )
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == project,
                ProjectActionGrantRow.recipient_principal_id
                == seed.actor.access.actor_principal_id.value,
                ProjectActionGrantRow.action == "create-access-groups",
            )
        )
    if candidate == "recovery":
        async with database.session() as session, session.begin():
            await PostgresIdentityRecoveryAdmissionWriter(
                session,
                installation_id=seed.actor.binding.installation_id,
                authority=identity.authority,
            ).reserve(
                IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
                )
            )
    if candidate == "eligible":
        assert (
            await change_membership(database, seed, revision=2, key="leave", remove=True)
        ).changed
    else:
        with pytest.raises(ConflictError):
            await change_membership(database, seed, revision=2, key="leave", remove=True)
        async with database.session() as session:
            assert await session.get(ProjectMembershipRow, (project, seed.bob_id.value)) is not None
            assert await session.scalar(select(ProjectRow.access_revision)) == 2


async def test_recovery_blocked_recipient_can_leave_but_cannot_rejoin(database: Database) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    identity = VerifiedHumanIdentityDTO(
        seed.actor.binding.identity.authority, IdentitySubject(str(UUID(int=200)))
    )
    async with database.session() as session, session.begin():
        await PostgresIdentityRecoveryAdmissionWriter(
            session,
            installation_id=seed.actor.binding.installation_id,
            authority=identity.authority,
        ).reserve(
            IdentityRecoveryEventDTO(
                IdentityRecoveryFlowId(uuid4()), identity, IdentityRecoveryEventKind.RECOVERY
            )
        )
    removed = await change_membership(database, seed, revision=2, key="leave", remove=True)
    assert removed.changed and removed.access_revision == 3
    with pytest.raises(ConflictError):
        await change_membership(database, seed, revision=3, key="blocked-rejoin")


async def test_self_departure_keeps_grants_assigned_to_remaining_human_and_blocks_later_replay(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    await change_membership(database, seed, revision=1, key="join")
    project = seed.project.project_id.value
    async with database.session() as session, session.begin():
        actions = (
            await session.scalars(
                select(ProjectActionGrantRow.action).where(
                    ProjectActionGrantRow.project_id == project
                )
            )
        ).all()
        for action in actions:
            session.add(
                ProjectActionGrantRow(
                    project_id=project,
                    recipient_principal_id=seed.bob_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action=action,
                    can_grant=True,
                    assigned_by_principal_id=seed.actor.access.actor_principal_id.value,
                )
            )
    left = await change_membership(
        database,
        seed,
        principal_id=seed.actor.access.actor_principal_id,
        revision=2,
        key="self-departure",
        remove=True,
    )
    assert left.changed
    with pytest.raises(ResourceNotFoundError):
        await change_membership(
            database,
            seed,
            principal_id=seed.actor.access.actor_principal_id,
            revision=2,
            key="self-departure",
            remove=True,
        )
    bob = seed.bob_access
    with pytest.raises(ConflictError):
        await change_membership(
            database, seed, revision=3, key="last-human", remove=True, access=bob
        )
