from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.enums.recovery_maintenance_mode import (
    RecoveryMaintenanceMode,
)
from inframeld_backend.access.infrastructure.readers.postgres_identity_recovery_cleanup_resume_facts_reader import (
    PostgresIdentityRecoveryCleanupResumeFactsReader,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


def _receipt_row(mode: str) -> HostMaintenanceReceiptRow:
    return HostMaintenanceReceiptRow(
        installation_id=uuid4(),
        operator_request_id="host-request",
        authority="kratos:test",
        subject="Alice",
        mode=mode,
        recovery_operation_id="original-recovery",
        operator_label="Deployment operator",
        reason="Hydra configuration repaired",
        authorized_at=datetime.now(UTC),
        outcome="cleanup-confirmed",
        released=False,
        run_id=None,
        deadline=None,
    )


@pytest.mark.asyncio
async def test_saved_mode_is_mapped_to_the_application_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _receipt_row("resume-recovery-cleanup")
    async with AsyncSession() as session, session.begin():
        monkeypatch.setattr(session, "get", AsyncMock(return_value=row))
        receipt = await PostgresIdentityRecoveryCleanupResumeFactsReader(session).receipt(
            installation_id=InstallationId(row.installation_id),
            operation_id=OperationId(row.operator_request_id),
        )

    assert receipt is not None
    assert receipt.mode is RecoveryMaintenanceMode.RESUME_RECOVERY_CLEANUP
    assert receipt.command.recovery_operation_id == OperationId("original-recovery")


@pytest.mark.asyncio
async def test_unrecognized_saved_mode_cannot_be_returned_as_a_valid_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulate invalid stored text without bypassing the real database constraint."""
    row = _receipt_row("unsupported-maintenance-mode")
    async with AsyncSession() as session, session.begin():
        monkeypatch.setattr(session, "get", AsyncMock(return_value=row))
        with pytest.raises(ValueError):
            await PostgresIdentityRecoveryCleanupResumeFactsReader(session).receipt(
                installation_id=InstallationId(row.installation_id),
                operation_id=OperationId(row.operator_request_id),
            )
