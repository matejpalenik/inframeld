"""Verify safe broader-repair storage before qualifying retained histories."""

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.project_metadata_scenarios import (
    seed_metadata_repair_recipient,
    seed_stranded_repair_target,
    stranded_repair_service,
)

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.value_objects.human_access_token_credential import (
    HumanAccessTokenCredential,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
    ProjectMetadataRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.stranded_authority_repair_receipt_row import (
    StrandedAuthorityRepairReceiptRow,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_safe_broader_repair_storage_is_available(database: Database) -> None:
    async with database.session() as session:
        connection = await session.connection()
        assert await connection.run_sync(
            lambda sync: inspect(sync).has_table("stranded_authority_repair_receipts")
        ), "Broader authority repair has no retained typed-original storage."
        columns = await connection.run_sync(
            lambda sync: frozenset(
                str(column["name"])
                for column in inspect(sync).get_columns("stranded_authority_repair_receipts")
            )
        )
        foreign_keys = await connection.run_sync(
            lambda sync: inspect(sync).get_foreign_keys("stranded_authority_repair_receipts")
        )
    assert columns == {
        "installation_id",
        "operator_request_id",
        "organization_id",
        "recipient_id",
        "expected_identity_id",
        "request_fingerprint",
        "before_revision",
        "after_revision",
        "responsibility_kind",
        "target_kind",
        "project_id",
        "access_group_id",
        "application_account_id",
        "action_id",
    }
    # Historical target and recipient IDs cannot restrict normal resource/relationship deletion.
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["referred_table"] == "host_maintenance_receipts"
    assert foreign_keys[0]["constrained_columns"] == ["installation_id", "operator_request_id"]
    assert foreign_keys[0]["referred_columns"] == ["installation_id", "operator_request_id"]
    assert foreign_keys[0].get("options", {}).get("ondelete") == "RESTRICT"


@pytest_asyncio.fixture
async def broader_original(database: Database) -> StrandedAuthorityRepairResultDTO:
    access, request, _ = await seed_stranded_repair_target(database, "group-manager")
    async with database.session() as session:
        return await stranded_repair_service(session).repair(access=access, command=request)


@pytest.mark.parametrize(
    "invalid",
    [
        "negative-before",
        "overflow-after",
        "revision-jump",
        "null-project",
        "null-group",
        "extra-account",
        "manager-action",
        "unknown-kind",
        "unknown-target",
        "short-fingerprint",
        "metadata-payload",
        "parent-namespace",
    ],
)
async def test_broader_original_constraints_are_null_safe_and_parent_bound(
    database: Database, broader_original: StrandedAuthorityRepairResultDTO, invalid: str
) -> None:
    async with database.session() as session, session.begin():
        change = update(StrandedAuthorityRepairReceiptRow).where(
            StrandedAuthorityRepairReceiptRow.installation_id
            == broader_original.installation_id.value,
            StrandedAuthorityRepairReceiptRow.operator_request_id
            == broader_original.operation_id.value,
        )
        if invalid == "negative-before":
            change = change.values(before_revision=-1)
        elif invalid == "overflow-after":
            change = change.values(before_revision=2**53 - 1, after_revision=2**53)
        elif invalid == "revision-jump":
            change = change.values(after_revision=broader_original.access_revision + 1)
        elif invalid == "null-project":
            change = change.values(project_id=None)
        elif invalid == "null-group":
            change = change.values(access_group_id=None)
        elif invalid == "extra-account":
            change = change.values(application_account_id=uuid4())
        elif invalid == "manager-action":
            change = change.values(action_id="add-documents")
        elif invalid == "unknown-kind":
            change = change.values(responsibility_kind="arbitrary")
        elif invalid == "unknown-target":
            change = change.values(target_kind="pipeline")
        elif invalid == "short-fingerprint":
            change = change.values(request_fingerprint=b"short")
        elif invalid == "metadata-payload":
            change = change.values(
                responsibility_kind="action-grantor",
                target_kind="project",
                access_group_id=None,
                action_id="edit-project-metadata",
            )
        else:
            change = change.values(installation_id=uuid4())
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(change)
        stored = await session.get(
            StrandedAuthorityRepairReceiptRow,
            (broader_original.installation_id.value, broader_original.operation_id.value),
            populate_existing=True,
        )
        assert (
            stored is not None
            and stored.after_revision == broader_original.access_revision
            and stored.responsibility_kind == "group-manager"
        )


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


async def test_retained_broader_original_refuses_destructive_downgrade(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    broader_original: StrandedAuthorityRepairResultDTO,
) -> None:
    with pytest.raises(RuntimeError, match="Retained stranded-authority repair originals"):
        command.downgrade(_config(temporary_postgres_settings), "0029_application_key_revocation")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0030_stranded_authority_repair"
        )
        row = await session.get(
            StrandedAuthorityRepairReceiptRow,
            (broader_original.installation_id.value, broader_original.operation_id.value),
        )
        assert row is not None and row.after_revision == broader_original.access_revision


async def test_empty_broader_history_round_trip_preserves_legacy_metadata_original(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    from uuid import UUID

    identity = VerifiedHumanIdentityDTO(
        IdentityAuthority("kratos:test"), IdentitySubject(str(uuid4()))
    )
    seed, binding = await seed_metadata_repair_recipient(database, identity)
    request = RepairStrandedAuthorityCommand(
        binding.installation_id,
        OperationId("legacy-before-upgrade"),
        ActionGrantorRepairResponsibilityDTO(
            ProjectGrantTargetDTO(seed.project_id), ActionId("edit-project-metadata")
        ),
        0,
        UUID(identity.subject.value),
        "Host operator",
        "Legacy metadata repair",
        HumanAccessTokenCredential("controlled-verification-proof"),
    )
    async with database.session() as session:
        original = await stranded_repair_service(session).repair(
            access=AccessContextDTO(seed.principal_id, binding), command=request
        )
    async with database.session() as session:
        stored = await session.get(
            ProjectMetadataRepairReceiptRow,
            (binding.installation_id.value, request.operation_id.value),
        )
        assert stored is not None
        fingerprint = stored.request_fingerprint
    for _ in range(2):
        command.downgrade(_config(temporary_postgres_settings), "0029_application_key_revocation")
        async with database.session() as session:
            assert (
                await session.scalar(select(AlembicVersionRow.version_num))
                == "0029_application_key_revocation"
            )
        command.upgrade(_config(temporary_postgres_settings), "head")
        async with database.session() as session:
            replay = await stranded_repair_service(session).repair(
                access=AccessContextDTO(seed.principal_id, binding), command=request
            )
            assert replay == original
        async with database.session() as session:
            stored = await session.get(
                ProjectMetadataRepairReceiptRow,
                (binding.installation_id.value, request.operation_id.value),
            )
            assert stored is not None and stored.request_fingerprint == fingerprint
            assert (
                await session.scalar(select(AlembicVersionRow.version_num))
                == "0030_stranded_authority_repair"
            )
