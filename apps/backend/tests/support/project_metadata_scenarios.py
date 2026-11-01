"""Assemble actual scoped metadata operations and seed explicit test authority."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.project_metadata_audit_writer import (
    ProjectMetadataAuditWriter,
)
from inframeld_backend.access.application.protocols.project_metadata_repair_facts_reader import (
    ProjectMetadataRepairFactsReader,
)
from inframeld_backend.access.application.services.project_metadata_authorization_service import (
    ProjectMetadataAuthorizationService,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.application.services.project_metadata_repair_service import (
    ProjectMetadataRepairService,
)
from inframeld_backend.access.application.services.project_metadata_service import (
    ProjectMetadataService,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_metadata_facts_reader import (
    PostgresProjectMetadataFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_metadata_repair_facts_reader import (
    PostgresProjectMetadataRepairFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_metadata_repository import (
    PostgresProjectMetadataRepository,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.writers.postgres_human_credential_state_initializer import (
    PostgresHumanCredentialStateInitializer,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_audit_writer import (
    PostgresProjectMetadataAuditWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_metadata_repair_writer import (
    PostgresProjectMetadataRepairWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)
from tests.support.access_scenarios import MockAccessScenarios, ProjectAuthorizationSeedDTO


def metadata_service(
    session: AsyncSession, audit: ProjectMetadataAuditWriter | None = None
) -> ProjectMetadataService:
    return ProjectMetadataService(
        transactions=SqlAlchemyTransactionManager(session),
        authorizer=ProjectMetadataAuthorizationService(PostgresProjectMetadataFactsReader(session)),
        idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        repository=PostgresProjectMetadataRepository(
            session, PostgresProjectMetadataAuditWriter(session) if audit is None else audit
        ),
        fingerprints=ProjectMetadataFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ),
    )


async def seed_metadata_project(session: AsyncSession) -> ProjectAuthorizationSeedDTO:
    seed = await MockAccessScenarios.seed_project_authorization(
        session, is_project_member=True, has_action_grant=False
    )
    session.add(
        ProjectActionGrantRow(
            project_id=seed.project_id.value,
            recipient_principal_id=seed.principal_id.value,
            recipient_kind=PrincipalKind.HUMAN,
            action="edit-project-metadata",
            can_grant=True,
        )
    )
    await session.flush()
    return ProjectAuthorizationSeedDTO(
        seed.organization_id, seed.principal_id, seed.project_id, ActionId("edit-project-metadata")
    )


async def seed_another_metadata_project(
    session: AsyncSession, original: ProjectAuthorizationSeedDTO
) -> ProjectAuthorizationSeedDTO:
    project_id = ProjectId(uuid4())
    session.add(
        ProjectRow(
            id=project_id.value,
            organization_id=original.organization_id.value,
            name="Other",
            status=ProjectStatus.ACTIVE,
        )
    )
    await session.flush()
    session.add(
        ProjectMembershipRow(
            project_id=project_id.value,
            principal_id=original.principal_id.value,
            organization_id=original.organization_id.value,
            principal_kind=PrincipalKind.HUMAN,
            application_principal_id=None,
        )
    )
    await session.flush()
    session.add(
        ProjectActionGrantRow(
            project_id=project_id.value,
            recipient_principal_id=original.principal_id.value,
            recipient_kind=PrincipalKind.HUMAN,
            action="edit-project-metadata",
            can_grant=True,
        )
    )
    await session.flush()
    return ProjectAuthorizationSeedDTO(
        original.organization_id, original.principal_id, project_id, original.action
    )


async def seed_legacy_project_authorization(session: AsyncSession) -> ProjectAuthorizationSeedDTO:
    """Seed real pre-0014 columns for the existing 0008 lookup upgrade scenario."""
    from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
    from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
    from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
    from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
    from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
    from tests.support.project_metadata_legacy_rows import LegacyProjectRow

    organization_id = OrganizationId(uuid4())
    principal_id = PrincipalId(uuid4())
    project_id = ProjectId(uuid4())
    session.add(OrganizationRow(id=organization_id.value, name="Support"))
    await session.flush()
    session.add(
        PrincipalRow(
            id=principal_id.value,
            organization_id=organization_id.value,
            kind=PrincipalKind.HUMAN,
            status=PrincipalStatus.ACTIVE,
            display_name="Alice",
        )
    )
    session.add(
        LegacyProjectRow(
            id=project_id.value,
            organization_id=organization_id.value,
            name="Support",
            status="active",
        )
    )
    await session.flush()
    session.add(
        ProjectMembershipRow(
            project_id=project_id.value,
            principal_id=principal_id.value,
            organization_id=organization_id.value,
            principal_kind=PrincipalKind.HUMAN,
            application_principal_id=None,
        )
    )
    await session.flush()
    return ProjectAuthorizationSeedDTO(
        organization_id, principal_id, project_id, ActionId("test-project-action")
    )


async def seed_metadata_repair_recipient(
    database: "Database", identity: "VerifiedHumanIdentityDTO"
) -> tuple[ProjectAuthorizationSeedDTO, "HumanOAuthCredentialBindingDTO"]:
    """Create a fresh test recipient with real generation initialization and no metadata grant."""
    async with database.session() as session, session.begin():
        principal = await MockAccessScenarios.seed_linked_human(session, identity)
        project_id = ProjectId(uuid4())
        session.add(
            ProjectRow(
                id=project_id.value,
                organization_id=principal.organization_id.value,
                name="Legacy Support",
                status=ProjectStatus.ACTIVE,
            )
        )
        await session.flush()
        session.add(
            ProjectMembershipRow(
                project_id=project_id.value,
                principal_id=principal.id.value,
                organization_id=principal.organization_id.value,
                principal_kind=PrincipalKind.HUMAN,
                application_principal_id=None,
            )
        )
    state = await PostgresHumanCredentialStateInitializer(database).initialize(identity)
    assert state.version is not None
    return (
        ProjectAuthorizationSeedDTO(
            principal.organization_id, principal.id, project_id, ActionId("edit-project-metadata")
        ),
        HumanOAuthCredentialBindingDTO(identity, state.installation_id, state.version),
    )


def metadata_repair_service(
    session: AsyncSession,
    audit: ProjectMetadataAuditWriter | None = None,
    *,
    facts: ProjectMetadataRepairFactsReader | None = None,
) -> "ProjectMetadataRepairService":
    return ProjectMetadataRepairService(
        transactions=SqlAlchemyTransactionManager(session),
        facts=PostgresProjectMetadataRepairFactsReader(session) if facts is None else facts,
        writer=PostgresProjectMetadataRepairWriter(
            session, PostgresProjectMetadataAuditWriter(session) if audit is None else audit
        ),
        fingerprints=ProjectMetadataFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ),
    )
