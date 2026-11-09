"""Assemble actual scoped metadata operations and seed explicit test authority."""

from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.project_metadata_audit_writer import (
    ProjectMetadataAuditWriter,
)
from inframeld_backend.access.application.protocols.stranded_authority_audit_writer import (
    StrandedAuthorityAuditWriter,
)
from inframeld_backend.access.application.protocols.stranded_authority_repair_facts_reader import (
    StrandedAuthorityRepairFactsReader,
)
from inframeld_backend.access.application.services.project_metadata_authorization_service import (
    ProjectMetadataAuthorizationService,
)
from inframeld_backend.access.application.services.project_metadata_fingerprint_service import (
    ProjectMetadataFingerprintService,
)
from inframeld_backend.access.application.services.project_metadata_service import (
    ProjectMetadataService,
)
from inframeld_backend.access.application.services.stranded_authority_fingerprint_service import (
    StrandedAuthorityFingerprintService,
)
from inframeld_backend.access.application.services.stranded_authority_repair_service import (
    StrandedAuthorityRepairService,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_metadata_facts_reader import (
    PostgresProjectMetadataFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_stranded_authority_repair_facts_reader import (
    PostgresStrandedAuthorityRepairFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_metadata_repository import (
    PostgresProjectMetadataRepository,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
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
from inframeld_backend.access.infrastructure.writers.postgres_stranded_authority_audit_writer import (
    PostgresStrandedAuthorityAuditWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_stranded_authority_repair_writer import (
    PostgresStrandedAuthorityRepairWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
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
from tests.support.access_group_scenarios import create_group
from tests.support.access_scenarios import MockAccessScenarios, ProjectAuthorizationSeedDTO
from tests.support.application_account_scenarios import create_account


def metadata_service(
    session: AsyncSession, audit: ProjectMetadataAuditWriter | None = None
) -> ProjectMetadataService:
    return ProjectMetadataService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        metadata_authorizer=ProjectMetadataAuthorizationService(
            PostgresProjectMetadataFactsReader(session)
        ),
        operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
        metadata_repository=PostgresProjectMetadataRepository(
            session, PostgresProjectMetadataAuditWriter(session) if audit is None else audit
        ),
        metadata_fingerprint_service=ProjectMetadataFingerprintService(
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


async def seed_stranded_repair_target(
    database: Database, kind: str, *, identity: VerifiedHumanIdentityDTO | None = None
) -> tuple[AccessContextDTO, RepairStrandedAuthorityCommand, bool]:
    if identity is None:
        identity = VerifiedHumanIdentityDTO(
            IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
        )
    seed, binding = await seed_metadata_repair_recipient(database, identity)
    access = AccessContextDTO(seed.principal_id, binding)
    revision = 0
    holder = False
    responsibility: GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO
    if kind in {"group-manager", "group-action"}:
        async with database.session() as session, session.begin():
            session.add(
                ProjectActionGrantRow(
                    project_id=seed.project_id.value,
                    recipient_principal_id=seed.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="create-access-groups",
                    can_grant=False,
                )
            )
        group = (await create_group(database, access, seed.project_id, revision=0)).group
        revision = group.access_revision
        if kind == "group-manager":
            async with database.session() as session, session.begin():
                await session.scalar(
                    select(ProjectRow.id)
                    .where(ProjectRow.id == seed.project_id.value)
                    .with_for_update()
                )
                await session.execute(
                    delete(GroupManagerRow).where(
                        GroupManagerRow.project_id == seed.project_id.value,
                        GroupManagerRow.group_id == group.group_id.value,
                    )
                )
                await session.execute(
                    delete(GroupMembershipRow).where(
                        GroupMembershipRow.project_id == seed.project_id.value,
                        GroupMembershipRow.group_id == group.group_id.value,
                    )
                )
                await session.execute(
                    update(ProjectRow)
                    .where(ProjectRow.id == seed.project_id.value)
                    .values(access_revision=ProjectRow.access_revision + 1)
                )
            revision += 1
            responsibility = GroupManagerRepairResponsibilityDTO(seed.project_id, group.group_id)
        else:
            # Native creation makes an eligible ordinary member+manager, with NO explicit document grant.
            async with database.session() as session:
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(GroupActionGrantRow)
                        .where(GroupActionGrantRow.group_id == group.group_id.value)
                    )
                    == 0
                )
                assert (
                    await session.get(
                        GroupManagerRow,
                        (seed.project_id.value, group.group_id.value, seed.principal_id.value),
                    )
                    is not None
                )
            responsibility = ActionGrantorRepairResponsibilityDTO(
                AccessGroupGrantTargetDTO(seed.project_id, group.group_id),
                ActionId("add-documents"),
            )
            holder = True
    elif kind == "application-account":
        async with database.session() as session, session.begin():
            session.add(
                ProjectActionGrantRow(
                    project_id=seed.project_id.value,
                    recipient_principal_id=seed.principal_id.value,
                    recipient_kind=PrincipalKind.HUMAN,
                    action="create-application-accounts",
                    can_grant=False,
                )
            )
        account = (await create_account(database, access, seed.project_id, revision=0)).account
        async with database.session() as session, session.begin():
            await session.scalar(
                select(ProjectRow.id)
                .where(ProjectRow.id == seed.project_id.value)
                .with_for_update()
            )
            await session.execute(
                delete(ApplicationActionGrantRow).where(
                    ApplicationActionGrantRow.project_id == seed.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == account.principal_id.value,
                    ApplicationActionGrantRow.action == "revoke-application-keys",
                )
            )
            await session.execute(
                update(ProjectRow)
                .where(ProjectRow.id == seed.project_id.value)
                .values(access_revision=ProjectRow.access_revision + 1)
            )
        revision = account.access_revision + 1
        responsibility = ActionGrantorRepairResponsibilityDTO(
            ApplicationAccountGrantTargetDTO(seed.project_id, account.principal_id),
            ActionId("revoke-application-keys"),
        )
    elif kind == "organization":
        responsibility = ActionGrantorRepairResponsibilityDTO(
            OrganizationGrantTargetDTO(seed.organization_id), ActionId("admit-users")
        )
    else:
        assert kind == "project"
        responsibility = ActionGrantorRepairResponsibilityDTO(
            ProjectGrantTargetDTO(seed.project_id), ActionId("manage-project-members")
        )
    request = RepairStrandedAuthorityCommand(
        binding.installation_id,
        OperationId("broader-original"),
        responsibility,
        revision,
        UUID(identity.subject.value),
        "Host operator",
        "Repair exact reviewed authority",
        HumanAccessTokenCredential("controlled-post-verification-proof"),
    )
    return access, request, holder


def stranded_repair_service(
    session: AsyncSession,
    audit: StrandedAuthorityAuditWriter | None = None,
    *,
    facts: StrandedAuthorityRepairFactsReader | None = None,
) -> StrandedAuthorityRepairService:
    """Use actual private repair adapters with the controlled test fingerprint key."""
    return StrandedAuthorityRepairService(
        transaction_manager=SqlAlchemyTransactionManager(session),
        repair_facts_reader=PostgresStrandedAuthorityRepairFactsReader(session)
        if facts is None
        else facts,
        repair_writer=PostgresStrandedAuthorityRepairWriter(
            session,
            PostgresStrandedAuthorityAuditWriter(
                session, PostgresProjectMetadataAuditWriter(session)
            )
            if audit is None
            else audit,
        ),
        repair_fingerprint_service=StrandedAuthorityFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
        ),
    )
