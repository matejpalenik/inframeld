from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from inframeld_backend.access.application.protocols.access_group_creator import AccessGroupCreator
from inframeld_backend.access.application.protocols.access_group_deleter import AccessGroupDeleter
from inframeld_backend.access.application.protocols.access_group_reader import AccessGroupReader
from inframeld_backend.access.application.protocols.access_group_relationship_changer import (
    AccessGroupRelationshipChanger,
)
from inframeld_backend.access.application.services.access_group_creation_fingerprint_service import (
    AccessGroupCreationFingerprintService,
)
from inframeld_backend.access.application.services.access_group_creation_service import (
    AccessGroupCreationService,
)
from inframeld_backend.access.application.services.access_group_deletion_service import (
    AccessGroupDeletionService,
)
from inframeld_backend.access.application.services.access_group_read_service import (
    AccessGroupReadService,
)
from inframeld_backend.access.application.services.access_group_relationship_service import (
    AccessGroupRelationshipService,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_creation_facts_reader import (
    PostgresAccessGroupCreationFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_creation_result_reader import (
    PostgresAccessGroupCreationResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_deletion_result_reader import (
    PostgresAccessGroupDeletionResultReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_facts_reader import (
    PostgresAccessGroupFactsReader,
)
from inframeld_backend.access.infrastructure.readers.postgres_access_group_relationship_result_reader import (
    PostgresAccessGroupRelationshipResultReader,
)
from inframeld_backend.access.infrastructure.writers.postgres_access_group_creation_writer import (
    PostgresAccessGroupCreationWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_access_group_deletion_writer import (
    PostgresAccessGroupDeletionWriter,
)
from inframeld_backend.access.infrastructure.writers.postgres_access_group_relationship_writer import (
    PostgresAccessGroupRelationshipWriter,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.writers.postgres_deletion_status_binding_writer import (
    PostgresDeletionStatusBindingWriter,
)
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)


@asynccontextmanager
async def open_access_group_creation(
    database: Database, fingerprints: RequestFingerprintService
) -> AsyncGenerator[AccessGroupCreator]:
    async with database.session() as session:
        yield AccessGroupCreationService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            creation_facts_reader=PostgresAccessGroupCreationFactsReader(session),
            creation_writer=PostgresAccessGroupCreationWriter(session),
            creation_result_reader=PostgresAccessGroupCreationResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            creation_fingerprint_service=AccessGroupCreationFingerprintService(fingerprints),
        )


@asynccontextmanager
async def open_access_group_read(database: Database) -> AsyncGenerator[AccessGroupReader]:
    async with database.session() as session:
        yield AccessGroupReadService(
            SqlAlchemyTransactionManager(session), PostgresAccessGroupFactsReader(session)
        )


@asynccontextmanager
async def open_access_group_relationship_change(
    database: Database, fingerprints: RequestFingerprintService
) -> AsyncGenerator[AccessGroupRelationshipChanger]:
    async with database.session() as session:
        yield AccessGroupRelationshipService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            group_change_facts_reader=PostgresAccessGroupFactsReader(session),
            group_relationship_writer=PostgresAccessGroupRelationshipWriter(session),
            group_relationship_result_reader=PostgresAccessGroupRelationshipResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            request_fingerprint_service=fingerprints,
        )


@asynccontextmanager
async def open_access_group_deletion(
    database: Database,
    fingerprints: RequestFingerprintService,
    profile: DeletionStatusRetentionProfile,
) -> AsyncGenerator[AccessGroupDeleter]:
    async with database.session() as session:
        yield AccessGroupDeletionService(
            transaction_manager=SqlAlchemyTransactionManager(session),
            group_deletion_facts_reader=PostgresAccessGroupFactsReader(session),
            group_deletion_writer=PostgresAccessGroupDeletionWriter(session),
            group_deletion_result_reader=PostgresAccessGroupDeletionResultReader(session),
            operation_idempotency=IdempotencyService(PostgresOperationReservationWriter(session)),
            request_fingerprint_service=fingerprints,
            deletion_status_binding_writer=PostgresDeletionStatusBindingWriter(session, profile),
        )
