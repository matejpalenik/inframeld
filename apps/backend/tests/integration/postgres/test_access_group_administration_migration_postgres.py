"""Preserve legacy group labels while adding scoped permanent Name bindings."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Text, Uuid, column, delete, func, insert, select, table
from sqlalchemy.exc import IntegrityError
from tests.support.access_group_scenarios import group_fingerprints
from tests.support.postgres import database_session
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.commands.delete_access_group_command import (
    DeleteAccessGroupCommand,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.infrastructure.rows.access_group_creation_result_row import (
    AccessGroupCreationResultRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_deletion_result_row import (
    AccessGroupDeletionResultRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_name_reservation_row import (
    AccessGroupNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_relationship_result_row import (
    AccessGroupRelationshipResultRow,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.bootstrap.access_group_composition import open_access_group_deletion
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


def test_legacy_group_label_survives_upgrade_downgrade_and_repeat_upgrade(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    settings = temporary_postgres_settings
    config = _config(settings)
    command.upgrade(config, "0024_application_accounts")
    organization, project, group = uuid4(), uuid4(), uuid4()
    label = " original unrestricted\nGroup label "
    legacy = table(
        "access_groups", column("id", Uuid()), column("project_id", Uuid()), column("name", Text())
    )
    with database_session(settings) as session, session.begin():
        session.add(OrganizationRow(id=organization, name="Legacy"))
        session.flush()
        session.add(
            ProjectRow(
                id=project, organization_id=organization, name="Legacy", status=ProjectStatus.ACTIVE
            )
        )
        session.flush()
        session.execute(insert(legacy).values(id=group, project_id=project, name=label))
    command.upgrade(config, "head")
    with database_session(settings) as session:
        stored = session.get(AccessGroupRow, group)
        assert stored is not None and stored.resource_name is None and stored.name == label
        assert (
            session.scalar(select(AlembicVersionRow.version_num))
            == "0030_stranded_authority_repair"
        )
    command.downgrade(config, "0024_application_accounts")
    with database_session(settings) as session:
        assert session.scalar(select(legacy.c.name).where(legacy.c.id == group)) == label
    command.upgrade(config, "head")
    with database_session(settings) as session:
        stored = session.get(AccessGroupRow, group)
        assert stored is not None and stored.resource_name is None


def test_named_group_requires_its_exact_scoped_binding_and_retirement_keeps_name_reserved(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    settings = temporary_postgres_settings
    config = _config(settings)
    command.upgrade(config, "head")
    organization, project, other_project, group = uuid4(), uuid4(), uuid4(), uuid4()
    with database_session(settings) as session, session.begin():
        session.add(OrganizationRow(id=organization, name="Names"))
        session.flush()
        session.add_all(
            [
                ProjectRow(
                    id=project,
                    organization_id=organization,
                    name="First",
                    status=ProjectStatus.ACTIVE,
                ),
                ProjectRow(
                    id=other_project,
                    organization_id=organization,
                    name="Second",
                    status=ProjectStatus.ACTIVE,
                ),
            ]
        )
        session.flush()
        session.add(
            AccessGroupNameReservationRow(
                project_id=project, name="support", organization_id=organization, group_id=group
            )
        )
        session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                AccessGroupRow(
                    id=group,
                    project_id=other_project,
                    name="Wrong Project",
                    resource_name="support",
                )
            )
            session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.add(
                AccessGroupRow(
                    id=uuid4(),
                    project_id=project,
                    name="Wrong identity",
                    resource_name="support",
                )
            )
            session.flush()
        session.add(
            AccessGroupRow(id=group, project_id=project, name="Support", resource_name="support")
        )
        session.flush()
    with pytest.raises(RuntimeError, match="Retained group identities"):
        command.downgrade(config, "0024_application_accounts")
    with database_session(settings) as session, session.begin():
        stored = session.get(AccessGroupRow, group)
        assert stored is not None
        session.delete(stored)
        reserved = session.get(AccessGroupNameReservationRow, (project, "support"))
        assert reserved is not None
        reserved.retired = True
        session.flush()
        with pytest.raises(IntegrityError), session.begin_nested():
            session.execute(
                insert(AccessGroupNameReservationRow).values(
                    project_id=project,
                    name="support",
                    organization_id=organization,
                    group_id=uuid4(),
                    retired=False,
                )
            )
        session.add(
            AccessGroupNameReservationRow(
                project_id=other_project,
                name="support",
                organization_id=organization,
                group_id=uuid4(),
            )
        )
    with database_session(settings) as session:
        assert (
            session.scalar(select(AlembicVersionRow.version_num))
            == "0030_stranded_authority_repair"
        )


@pytest.mark.asyncio
async def test_retained_legacy_group_deletion_status_prevents_unsafe_downgrade(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    group_id = AccessGroupId(uuid4())
    async with database.session() as session, session.begin():
        session.add(
            AccessGroupRow(id=group_id.value, project_id=project.project_id.value, name="Legacy")
        )
        await session.flush()
        session.add(
            GroupMembershipRow(
                project_id=project.project_id.value,
                group_id=group_id.value,
                principal_id=seed.access.actor_principal_id.value,
            )
        )
        await session.flush()
        session.add(
            GroupManagerRow(
                project_id=project.project_id.value,
                group_id=group_id.value,
                principal_id=seed.access.actor_principal_id.value,
                principal_kind=PrincipalKind.HUMAN,
            )
        )

    async with open_access_group_deletion(
        database, group_fingerprints(), DeletionStatusRetentionProfile(30)
    ) as service:
        removed = await service.delete(
            access=seed.access,
            command=DeleteAccessGroupCommand(project.project_id, group_id, 1),
            context=IdempotencyContextDTO(
                HttpMethod.DELETE,
                f"/v1/projects/{project.project_id.value}/access-groups/{group_id.value}",
                IdempotencyKey("delete-legacy-group"),
            ),
            request_id=RequestId(uuid4()),
        )
    operation_id = removed.operation.operation_id.value
    async with database.session() as session, session.begin():
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == operation_id
            )
        )
    async with database.session() as session:
        assert await session.get(AccessGroupRow, group_id.value) is None
        assert await session.get(IdempotencyReservationRow, operation_id) is None
        assert await session.get(DeletionStatusBindingRow, operation_id) is not None
        assert await session.get(DeletionStatusObservationRow, operation_id) is not None
        for row in (
            AccessGroupNameReservationRow,
            AccessGroupCreationResultRow,
            AccessGroupRelationshipResultRow,
            AccessGroupDeletionResultRow,
        ):
            assert await session.scalar(select(func.count()).select_from(row)) == 0

    with pytest.raises(RuntimeError, match="Retained group"):
        command.downgrade(_config(temporary_postgres_settings), "0024_application_accounts")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0030_stranded_authority_repair"
        )
        assert await session.get(DeletionStatusBindingRow, operation_id) is not None
        assert await session.get(DeletionStatusObservationRow, operation_id) is not None
