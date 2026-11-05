"""Reuse first-administrator admission and real creation adapters for PostgreSQL cases."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.create_project_command import (
    CreateProjectCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_creation_result_dto import (
    ProjectCreationResultDTO,
)
from inframeld_backend.access.application.services.project_creation_authorization_service import (
    ProjectCreationAuthorizationService,
)
from inframeld_backend.access.application.services.project_creation_fingerprint_service import (
    ProjectCreationFingerprintService,
)
from inframeld_backend.access.application.services.project_creation_service import (
    ProjectCreationService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.infrastructure.readers.postgres_organization_access_facts_reader import (
    PostgresOrganizationAccessFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_creation_result_reader import (
    PostgresProjectCreationResultReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_creation_operation_result_row import (
    ProjectCreationOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_name_reservation_row import (
    ProjectNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_project_creation_writer import (
    PostgresProjectCreationWriter,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
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
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.first_administrator_bootstrap_scenarios import (
    bootstrap_scenario,
    bootstrap_service,
)

INITIAL_ACTIONS = (
    "manage-project-members",
    "create-access-groups",
    "create-application-accounts",
    "create-pipelines",
    "create-deployments",
    "manage-upload-defaults",
    "delete-project",
    "inspect-budget",
    "manage-budget",
    "manage-trace-policy",
    "delete-trace-history",
    "inspect-feedback",
    "create-collections",
    "create-sources",
    "create-model-connections",
    "create-processing-profiles",
    "create-embedding-profiles",
    "edit-project-metadata",
)


@dataclass(frozen=True, slots=True)
class ProjectCreationSeedDTO:
    access: AccessContextDTO
    organization_id: OrganizationId
    access_revision: int
    binding: HumanOAuthCredentialBindingDTO


async def seed_project_creator(database: Database) -> ProjectCreationSeedDTO:
    """Admit the first human through the delivered bootstrap with controlled provider proof."""
    scenario = await bootstrap_scenario(database)
    async with database.session() as session:
        result = await bootstrap_service(session, scenario.binding).bootstrap(scenario.command)
    return ProjectCreationSeedDTO(
        AccessContextDTO(
            result.recipient_id, MockAuthenticationEvidence.browser(scenario.binding.identity)
        ),
        result.organization_id,
        result.access_revision,
        scenario.binding,
    )


def creation_command(seed: ProjectCreationSeedDTO, name: str = "support") -> CreateProjectCommand:
    return CreateProjectCommand(
        seed.organization_id,
        seed.access_revision,
        ResourceName(name),
        SubmittedDisplayName("Support"),
    )


def creation_context(key: str = "original") -> IdempotencyContextDTO:
    return IdempotencyContextDTO("POST", "/v1/projects", IdempotencyKey(key))


def creation_fingerprints() -> ProjectCreationFingerprintService:
    return ProjectCreationFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    )


def creation_service(
    session: AsyncSession, idempotency: OperationIdempotency | None = None
) -> ProjectCreationService:
    return ProjectCreationService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        creation_authorizer=ProjectCreationAuthorizationService(
            PostgresOrganizationAccessFactsReader(session)
        ),
        creation_writer=PostgresProjectCreationWriter(session),
        creation_result_reader=PostgresProjectCreationResultReader(session),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session))
        if idempotency is None
        else idempotency,
        creation_fingerprint_service=creation_fingerprints(),
    )


async def create_project(
    database: Database,
    seed: ProjectCreationSeedDTO,
    *,
    name: str = "support",
    key: str = "original",
) -> ProjectCreationResultDTO:
    async with database.session() as session:
        return await creation_service(session).create(
            access=seed.access, command=creation_command(seed, name), context=creation_context(key)
        )


async def assert_created_project(database: Database, result: ProjectCreationResultDTO) -> None:
    """Check persisted values independently of the production policy and HTTP mapper."""
    project = result.project
    async with database.session() as session:
        row = await session.get(ProjectRow, project.project_id.value)
        assert row is not None
        assert (row.organization_id, row.resource_name, row.name, row.status) == (
            project.organization_id.value,
            project.name.value,
            project.display_name,
            ProjectStatus.ACTIVE,
        )
        assert (row.access_revision, row.metadata_revision) == (1, 0)
        membership = await session.get(
            ProjectMembershipRow, (project.project_id.value, project.creator_principal_id.value)
        )
        assert membership is not None
        assert membership.organization_id == project.organization_id.value
        assert membership.principal_kind is PrincipalKind.HUMAN
        assert membership.assigned_by_principal_id == project.creator_principal_id.value
        grants = (
            await session.scalars(
                select(ProjectActionGrantRow).where(
                    ProjectActionGrantRow.project_id == project.project_id.value
                )
            )
        ).all()
        assert len(grants) == 18
        assert {grant.action for grant in grants} == set(INITIAL_ACTIONS)
        assert all(
            grant.recipient_principal_id == project.creator_principal_id.value
            and grant.recipient_kind is PrincipalKind.HUMAN
            and grant.can_grant
            and grant.assigned_by_principal_id == project.creator_principal_id.value
            for grant in grants
        )
        name = await session.get(
            ProjectNameReservationRow, (project.organization_id.value, project.name.value)
        )
        assert name is not None and name.project_id == project.project_id.value
        assert name.binding_revision == 0 and not name.retired
        original = await session.get(ProjectCreationOperationResultRow, project.operation_id.value)
        assert original is not None
        assert (original.organization_id, original.project_id, original.creator_principal_id) == (
            project.organization_id.value,
            project.project_id.value,
            project.creator_principal_id.value,
        )
        assert (
            original.name,
            original.display_name,
            original.access_revision,
            original.metadata_revision,
        ) == (project.name.value, project.display_name, 1, 0)
        assert tuple(original.initial_actions) == INITIAL_ACTIONS
        reservation = await session.get(IdempotencyReservationRow, project.operation_id.value)
        assert reservation is not None and reservation.project_id is None
        assert reservation.organization_id == project.organization_id.value
        assert reservation.principal_id == project.creator_principal_id.value
        assert (reservation.method, reservation.requested_route) == ("POST", "/v1/projects")
        assert (reservation.lookup_authority_family, reservation.lookup_action_id) == (
            "organization_action_use",
            "create-projects",
        )
        assert reservation.state is OperationReservationState.REPLAYABLE
        assert reservation.expires_at == result.operation.expires_at
        audit = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == project.operation_id.value
                )
            )
        ).one()
        assert (audit.event_type, audit.target_kind, audit.target_id) == (
            "project_created",
            "project",
            project.project_id.value,
        )
        assert (
            audit.actor_kind == "human"
            and audit.actor_principal_id == project.creator_principal_id.value
        )
        assert audit.affected_principal_id == project.creator_principal_id.value
        assert audit.after_values == {
            "name": project.name.value,
            "display_name": project.display_name,
            "access_revision": 1,
            "metadata_revision": 0,
            "initial_actions": list(INITIAL_ACTIONS),
        }
        assert (
            await session.scalar(
                select(OrganizationRow.access_revision).where(
                    OrganizationRow.id == project.organization_id.value
                )
            )
            == 1
        )
