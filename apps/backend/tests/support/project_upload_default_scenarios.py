"""Compose real Project/group producers with the future-default adapters under test."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.set_project_upload_default_command import (
    SetProjectUploadDefaultCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.created_access_group_dto import CreatedAccessGroupDTO
from inframeld_backend.access.application.dtos.project_upload_default_change_result_dto import (
    ProjectUploadDefaultChangeResultDTO,
)
from inframeld_backend.access.application.services.project_upload_default_fingerprint_service import (
    ProjectUploadDefaultFingerprintService,
)
from inframeld_backend.access.application.services.project_upload_default_service import (
    ProjectUploadDefaultService,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
from inframeld_backend.access.infrastructure.readers.postgres_project_upload_default_facts_reader import (
    PostgresProjectUploadDefaultFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_upload_default_repository import (
    PostgresProjectUploadDefaultRepository,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.project_upload_default_group_row import (
    ProjectUploadDefaultGroupRow,
)
from inframeld_backend.access.infrastructure.rows.project_upload_default_result_row import (
    ProjectUploadDefaultResultRow,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from tests.support.access_group_scenarios import create_group, group_fingerprints
from tests.support.project_creation_scenarios import ProjectCreationSeedDTO
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)


@dataclass(frozen=True, slots=True)
class UploadDefaultScenario:
    actor: ProjectCreationSeedDTO
    project_id: ProjectId
    groups: tuple[CreatedAccessGroupDTO, ...]
    bob_id: PrincipalId

    @property
    def revision(self) -> int:
        return self.groups[-1].access_revision


async def seed_upload_default_scenario(database: Database) -> UploadDefaultScenario:
    seed = await seed_membership_project(database)
    actor, project = seed.actor, seed.project
    joined = await change_membership(
        database, seed, revision=project.access_revision, key="join-upload-member"
    )
    groups: list[CreatedAccessGroupDTO] = []
    revision = joined.access_revision
    for index, name in enumerate(("support-docs", "hr-docs", "engineering-docs")):
        group = (
            await create_group(
                database, actor.access, project.project_id, revision, name, key=f"group-{index}"
            )
        ).group
        groups.append(group)
        revision = group.access_revision
    return UploadDefaultScenario(actor, project.project_id, tuple(groups), seed.bob_id)


def upload_default_service(session: AsyncSession) -> ProjectUploadDefaultService:
    return ProjectUploadDefaultService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        default_facts_reader=PostgresProjectUploadDefaultFactsReader(session),
        default_repository=PostgresProjectUploadDefaultRepository(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        default_fingerprint_service=ProjectUploadDefaultFingerprintService(group_fingerprints()),
    )


def upload_default_context(
    project_id: ProjectId, key: str = "default-original"
) -> IdempotencyContextDTO:
    return IdempotencyContextDTO(
        HttpMethod.PUT, f"/v1/projects/{project_id.value}/upload-defaults", IdempotencyKey(key)
    )


async def replace_upload_default(
    database: Database,
    scenario: UploadDefaultScenario,
    indexes: tuple[int, ...],
    revision: int,
    key: str = "default-original",
    access: AccessContextDTO | None = None,
) -> ProjectUploadDefaultChangeResultDTO:
    async with database.session() as session:
        return await upload_default_service(session).set(
            access=scenario.actor.access if access is None else access,
            command=SetProjectUploadDefaultCommand(
                scenario.project_id,
                UploadAudience(tuple(scenario.groups[index].group_id for index in indexes)),
                revision,
            ),
            context=upload_default_context(scenario.project_id, key),
        )


async def upload_default_effects(
    database: Database, project_id: ProjectId
) -> tuple[tuple[UUID, ...], int | None, int, int, int]:
    async with database.session() as session:
        groups = tuple(
            await session.scalars(
                select(ProjectUploadDefaultGroupRow.group_id)
                .where(ProjectUploadDefaultGroupRow.project_id == project_id.value)
                .order_by(ProjectUploadDefaultGroupRow.group_id)
            )
        )
        revision = await session.scalar(
            select(ProjectRow.access_revision).where(ProjectRow.id == project_id.value)
        )
        audit = await session.scalar(
            select(func.count())
            .select_from(AccessAuditEventRow)
            .where(
                AccessAuditEventRow.project_id == project_id.value,
                AccessAuditEventRow.event_type == "project_upload_default_changed",
            )
        )
        originals = await session.scalar(
            select(func.count())
            .select_from(ProjectUploadDefaultResultRow)
            .where(ProjectUploadDefaultResultRow.project_id == project_id.value)
        )
        reservations = await session.scalar(
            select(func.count())
            .select_from(IdempotencyReservationRow)
            .where(
                IdempotencyReservationRow.project_id == project_id.value,
                IdempotencyReservationRow.requested_route
                == f"/v1/projects/{project_id.value}/upload-defaults",
            )
        )
        assert audit is not None and originals is not None and reservations is not None
        return groups, revision, audit, originals, reservations
