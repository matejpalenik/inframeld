from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.invitation_activator import InvitationActivator
from inframeld_backend.access.application.protocols.invitation_previewer import InvitationPreviewer
from inframeld_backend.access.application.services.invitation_activation_service import (
    InvitationActivationService,
)
from inframeld_backend.access.application.services.invitation_administration_service import (
    InvitationAdministrationService,
)
from inframeld_backend.access.application.services.invitation_assignment_service import (
    InvitationAssignmentService,
)
from inframeld_backend.access.application.services.invitation_fingerprint_service import (
    InvitationFingerprintService,
)
from inframeld_backend.access.application.services.invitation_preview_service import (
    InvitationPreviewService,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_assignment_facts_reader import (
    PostgresInvitationAssignmentFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_binding_reader import (
    PostgresInvitationBindingReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_facts_reader import (
    PostgresInvitationFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_membership_repository import (
    PostgresProjectMembershipRepository,
)
from inframeld_backend.access.infrastructure.settings.invitation_settings import InvitationSettings
from inframeld_backend.access.infrastructure.writers.postgres_access_group_action_grant_writer import (
    PostgresAccessGroupActionGrantWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_access_group_relationship_writer import (
    PostgresAccessGroupRelationshipWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_application_account_action_grant_writer import (
    PostgresApplicationAccountActionGrantWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_human_admission_writer import (
    PostgresHumanAdmissionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_invitation_model_connection_grant_writer import (
    PostgresInvitationModelConnectionGrantWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_invitation_writer import (
    PostgresInvitationWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_organization_action_grant_writer import (
    PostgresOrganizationActionGrantWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_project_membership_change_writer import (
    PostgresProjectMembershipChangeWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_invitation_administration(
    database: Database, fingerprints: InvitationFingerprintService, settings: InvitationSettings
) -> AsyncGenerator[InvitationAdministrationService]:
    """Close the request-local session around exact human issuance or revocation."""
    async with database.session() as session:
        yield InvitationAdministrationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            invitation_facts_reader=PostgresInvitationFactsReader(session),
            invitation_writer=PostgresInvitationWriter(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            invitation_fingerprint_service=fingerprints,
            default_lifetime_seconds=settings.default_lifetime_seconds,
            maximum_lifetime_seconds=settings.maximum_lifetime_seconds,
        )


@asynccontextmanager
async def open_invitation_preview(database: Database) -> AsyncGenerator[InvitationPreviewer]:
    """Read intended scope in one session without admitting or reserving the recipient."""
    async with database.session() as session:
        yield InvitationPreviewService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            invitation_preview_facts_reader=PostgresInvitationBindingReader(session),
        )


@asynccontextmanager
async def open_invitation_activation(
    database: Database, fingerprints: InvitationFingerprintService
) -> AsyncGenerator[InvitationActivator]:
    """Keep all native owners in the activation caller's one session and transaction."""
    async with database.session() as session:
        audit = PostgresAuditEventWriter(session)
        facts = PostgresInvitationAssignmentFactsReader(session)
        assignments = InvitationAssignmentService(
            invitation_assignment_facts_reader=facts,
            invitation_project_membership_writer=PostgresProjectMembershipChangeWriter(session),
            invitation_group_relationship_writer=PostgresAccessGroupRelationshipWriter(session),
            invitation_organization_grant_writer=PostgresOrganizationActionGrantWriter(
                session, audit
            ),
            invitation_access_group_grant_writer=PostgresAccessGroupActionGrantWriter(
                session, audit
            ),
            invitation_application_grant_writer=PostgresApplicationAccountActionGrantWriter(
                session, audit
            ),
            project_membership_repository=PostgresProjectMembershipRepository(session, audit),
            invitation_model_connection_grant_writer=PostgresInvitationModelConnectionGrantWriter(
                session
            ),
        )
        yield InvitationActivationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            invitation_assignment_facts_reader=facts,
            invitation_activation_operation_store=PostgresInvitationWriter(session),
            invitation_fingerprint_service=fingerprints,
            invitation_admission_writer=PostgresHumanAdmissionWriter(session),
            invitation_assignment_service=assignments,
        )
