"""Assemble real grant behavior with optional controls for failure and race scenarios."""

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.protocols.audit_event_writer import AuditEventWriter
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.services.project_grant_authorization_service import (
    ProjectGrantAuthorizationService,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.application.services.project_grant_change_service import (
    ProjectGrantChangeService,
)
from inframeld_backend.access.infrastructure.readers.postgres_project_grant_change_facts_reader import (
    PostgresProjectGrantChangeFactsReader,
)
from inframeld_backend.access.infrastructure.repositories.postgres_project_membership_repository import (
    PostgresProjectMembershipRepository,
)
from inframeld_backend.access.infrastructure.writers.postgres_audit_event_writer import (
    PostgresAuditEventWriter,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


def create_project_grant_change_service(
    session: AsyncSession,
    *,
    authorizer: ProjectGrantAuthorizer | None = None,
    audit_events: AuditEventWriter | None = None,
    idempotency: OperationIdempotency | None = None,
) -> ProjectGrantChangeService:
    return ProjectGrantChangeService(
        transactions=SqlAlchemyTransactionManager(session),
        authorizer=authorizer
        if authorizer is not None
        else ProjectGrantAuthorizationService(PostgresProjectGrantChangeFactsReader(session)),
        idempotency=idempotency
        if idempotency is not None
        else IdempotencyService(PostgresOperationReservationWriter(session)),
        memberships=PostgresProjectMembershipRepository(
            session, audit_events if audit_events is not None else PostgresAuditEventWriter(session)
        ),
        fingerprints=ProjectGrantChangeFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"T" * 32))
        ),
    )
