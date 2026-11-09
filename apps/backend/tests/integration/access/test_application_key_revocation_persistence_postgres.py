"""Qualify atomic revocation and safe originals through the actual shared transaction."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from tests.support.application_key_scenarios import issue_application_key, revocation_service

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_issue_result_dto import (
    ApplicationKeyIssueResultDTO,
)
from inframeld_backend.access.infrastructure.readers.postgres_application_key_revocation_facts_reader import (
    PostgresApplicationKeyRevocationFactsReader,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.application_key_revocation_result_row import (
    ApplicationKeyRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


@pytest_asyncio.fixture
async def issued_key(
    database: Database,
) -> tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]:
    return await issue_application_key(database)


async def test_absent_revocation_original_returns_no_result(
    database: Database, issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]
) -> None:
    creator, issued = issued_key
    metadata = issued.original.metadata
    async with database.session() as session, session.begin():
        reader = PostgresApplicationKeyRevocationFactsReader(session)
        facts = await reader.lock_for_revoke(
            access=creator,
            command=RevokeApplicationKeyCommand(
                metadata.project_id,
                metadata.application_principal_id,
                metadata.key_id,
                issued.original.access_revision,
            ),
        )
        assert facts is not None and facts.actor.has_exact_action_grant
        assert (
            await reader.read_original(
                organization_id=facts.organization_id,
                project_id=facts.project_id,
                actor_principal_id=creator.actor_principal_id,
                operation_id=OperationId(str(uuid4())),
            )
            is None
        )


async def test_revoke_commits_key_revision_audit_original_and_completion_atomically(
    database: Database, issued_key: tuple[AccessContextDTO, ApplicationKeyIssueResultDTO]
) -> None:
    creator, issued = issued_key
    metadata = issued.original.metadata
    credential = issued.credential
    assert credential is not None
    context = IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/projects/{metadata.project_id.value}/application-accounts/{metadata.application_principal_id.value}/keys/{metadata.key_id.value}/revoke",
        IdempotencyKey("revoke-original"),
    )
    async with database.session() as session:
        result = await revocation_service(session).revoke(
            access=creator,
            command=RevokeApplicationKeyCommand(
                metadata.project_id,
                metadata.application_principal_id,
                metadata.key_id,
                issued.original.access_revision,
            ),
            context=context,
        )
    assert result.operation.created
    assert result.original.metadata.revoked_at is not None
    assert result.original.access_revision == issued.original.access_revision + 1

    async with database.session() as session:
        key = await session.get(ApplicationKeyRow, metadata.key_id.value)
        original = await session.get(
            ApplicationKeyRevocationResultRow, result.operation.operation_id.value
        )
        reservation = await session.get(
            IdempotencyReservationRow, result.operation.operation_id.value
        )
        assert key is not None and key.revoked_at == result.original.metadata.revoked_at
        assert key.verifier == credential.digest()
        assert original is not None
        assert original.key_id == key.key_id and original.revoked_at == key.revoked_at
        assert original.before_revision == issued.original.access_revision
        assert original.access_revision == result.original.access_revision
        assert original.actor_principal_id == creator.actor_principal_id.value
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == metadata.project_id.value)
            )
            == result.original.access_revision
        )
        assert reservation is not None
        assert reservation.state is OperationReservationState.REPLAYABLE
        assert reservation.replay_kind is OperationReplayKind.SAFE_RESULT
        audits = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.correlation_id == result.operation.operation_id.value,
                    AccessAuditEventRow.event_type == "application_key_revoked",
                )
            )
        ).all()
        assert len(audits) == 1
        assert audits[0].target_id == key.key_id
