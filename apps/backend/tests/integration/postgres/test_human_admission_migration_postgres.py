"""Require admission schema without applying an empty revision as a TDD scaffold."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.first_administrator_bootstrap_scenarios import MockBootstrapIdentityVerifier
from tests.support.postgres import database_connection
from tests.support.project_creation_scenarios import seed_project_creator

from inframeld_backend.access.application.commands.admit_human_command import AdmitHumanCommand
from inframeld_backend.access.application.dtos.human_admission_result_dto import (
    HumanAdmissionResultDTO,
)
from inframeld_backend.access.application.services.human_admission_fingerprint_service import (
    HumanAdmissionFingerprintService,
)
from inframeld_backend.access.infrastructure.readers.postgres_human_admission_result_reader import (
    PostgresHumanAdmissionResultReader,
)
from inframeld_backend.access.infrastructure.rows.first_administrator_bootstrap_receipt_row import (
    FirstAdministratorBootstrapReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_admission_operation_result_row import (
    HumanAdmissionOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.bootstrap.human_admission_composition import open_human_admission
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    SUPPORTED_SCHEMA_REVISION,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


def _configuration(settings: DatabaseSettings) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = settings
    return config


async def _require_schema(database: Database) -> None:
    """Fail intentionally on the missing requirement before querying any new table."""
    async with database.session() as session:
        current = await session.scalar(select(AlembicVersionRow.version_num))
    assert current == SUPPORTED_SCHEMA_REVISION, "Required current schema is not installed."


async def _admitted(database: Database) -> HumanAdmissionResultDTO:
    seed = await seed_project_creator(database)
    fingerprints = HumanAdmissionFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"a" * 32))
    )
    async with open_human_admission(
        database, fingerprints, MockBootstrapIdentityVerifier(), seed.binding.identity.authority, 5
    ) as service:
        return await service.admit(
            access=seed.access,
            command=AdmitHumanCommand(seed.organization_id, UUID(int=200), seed.access_revision),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/organizations/{seed.organization_id.value}/human-admissions",
                IdempotencyKey("admit-bob"),
            ),
        )


async def test_required_schema_adds_result_storage_without_changing_existing_admission(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    await _require_schema(database)
    seed = await seed_project_creator(database)
    with database_connection(temporary_postgres_settings) as connection:
        assert inspect(connection).has_table("human_admission_operation_results")
    config = _configuration(temporary_postgres_settings)
    for _ in range(2):
        command.downgrade(config, "0018_spending_accounting")
        run_migrations(temporary_postgres_settings)
        await _require_schema(database)
        async with database.session() as session:
            claim = await session.get(
                FirstAdministratorBootstrapReceiptRow, seed.binding.installation_id.value
            )
            assert claim is not None and claim.recipient_id == seed.access.actor_principal_id.value
            assert await session.get(PrincipalRow, claim.recipient_id) is not None
            link = await session.get(
                HumanIdentityLinkRow,
                (seed.binding.identity.authority.value, seed.binding.identity.subject.value),
            )
            assert link is not None and link.principal_id == claim.recipient_id
            generation = await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    seed.binding.identity.authority.value,
                    seed.binding.identity.subject.value,
                ),
            )
            assert generation is not None and generation.version == seed.binding.version.value
            assert await session.scalar(select(OrganizationRow.access_revision)) == 1
            assert (
                await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow))
                == 4
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(HumanAdmissionOperationResultRow)
                )
                == 0
            )


@pytest.mark.parametrize(
    "corruption",
    [
        "installation",
        "authority",
        "subject",
        "organization",
        "actor",
        "principal",
        "before-revision",
        "result-revision",
        "status",
        "changed",
    ],
)
async def test_result_insert_constraints_bind_parent_identity_scope_and_original_status(
    database: Database, corruption: str
) -> None:
    await _require_schema(database)
    first = await _admitted(database)
    async with database.session() as session, session.begin():
        original = await session.get(
            HumanAdmissionOperationResultRow, first.operation.operation_id.value
        )
        parent = await session.get(IdempotencyReservationRow, first.operation.operation_id.value)
        assert original is not None and parent is not None
        operation_id = str(uuid4())
        session.add(
            IdempotencyReservationRow(
                operation_id=operation_id,
                principal_id=parent.principal_id,
                organization_id=parent.organization_id,
                project_id=None,
                method=parent.method,
                requested_route=parent.requested_route,
                request_key="constraint-insert",
                request_fingerprint=parent.request_fingerprint,
                lookup_authority_family=parent.lookup_authority_family,
                lookup_action_id=parent.lookup_action_id,
            )
        )
        await session.flush()
        candidate = replace(original, operation_id=operation_id)
        if corruption == "installation":
            candidate.installation_id = uuid4()
        elif corruption == "authority":
            candidate.authority = "different-authority"
        elif corruption == "subject":
            candidate.subject = str(uuid4())
        elif corruption == "organization":
            candidate.organization_id = uuid4()
        elif corruption == "actor":
            candidate.actor_principal_id = first.principal_id.value
        elif corruption == "principal":
            candidate.principal_id = first.actor_principal_id.value
        elif corruption == "before-revision":
            candidate.before_revision = 0
        elif corruption == "result-revision":
            candidate.access_revision = -1
        elif corruption == "status":
            candidate.status_code = 202
        else:
            candidate.changed = False
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(candidate)
                await session.flush()
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 1
        )
        assert await session.get(PrincipalRow, first.principal_id.value) is not None


async def test_retained_original_result_refuses_downgrade_without_losing_admission_or_receipt(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    await _require_schema(database)
    first = await _admitted(database)
    with pytest.raises(RuntimeError, match="Retained human admission outcomes"):
        command.downgrade(_configuration(temporary_postgres_settings), "0018_spending_accounting")
    await _require_schema(database)
    async with database.session() as session, session.begin():
        assert await session.get(PrincipalRow, first.principal_id.value) is not None
        replay = await PostgresHumanAdmissionResultReader(session).original(
            installation_id=first.installation_id,
            identity=first.identity,
            organization_id=first.organization_id,
            actor_id=first.actor_principal_id,
            operation=replace(first.operation, created=False),
        )
        assert replay == replace(first, operation=replace(first.operation, created=False))


async def test_expired_parent_cleanup_removes_only_result_and_allows_safe_downgrade(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    await _require_schema(database)
    first = await _admitted(database)
    async with database.session() as session, session.begin():
        await session.execute(
            update(IdempotencyReservationRow)
            .where(IdempotencyReservationRow.operation_id == first.operation.operation_id.value)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    async with database.session() as session, session.begin():
        with pytest.raises(ConflictError):
            await PostgresHumanAdmissionResultReader(session).original(
                installation_id=first.installation_id,
                identity=first.identity,
                organization_id=first.organization_id,
                actor_id=first.actor_principal_id,
                operation=replace(first.operation, created=False),
            )
    async with database.session() as session, session.begin():
        # Exercise ordinary expired-parent deletion, not a new retention service.
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == first.operation.operation_id.value,
                IdempotencyReservationRow.expires_at <= func.clock_timestamp(),
            )
        )
        assert (
            await session.scalar(select(func.count()).select_from(HumanAdmissionOperationResultRow))
            == 0
        )
        assert await session.get(PrincipalRow, first.principal_id.value) is not None
        link = await session.get(
            HumanIdentityLinkRow, (first.identity.authority.value, first.identity.subject.value)
        )
        assert link is not None and link.principal_id == first.principal_id.value
        version = await session.get(
            HumanCredentialVersionRow,
            (
                first.installation_id.value,
                first.identity.authority.value,
                first.identity.subject.value,
            ),
        )
        assert version is not None and version.version == 1
    command.downgrade(_configuration(temporary_postgres_settings), "0018_spending_accounting")
    async with database.session() as session:
        assert await session.get(PrincipalRow, first.principal_id.value) is not None
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0018_spending_accounting"
        )
