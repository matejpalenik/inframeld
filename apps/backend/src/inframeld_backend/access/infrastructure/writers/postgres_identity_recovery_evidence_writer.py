from datetime import datetime
from typing import override
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_settings_evidence_dto import (
    IdentityRecoverySettingsEvidenceDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.application.enums.identity_recovery_run_source import (
    IdentityRecoveryRunSource,
)
from inframeld_backend.access.application.protocols.identity_recovery_evidence_writer import (
    IdentityRecoveryEvidenceWriter,
)
from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
    IdentityRecoveryEvidenceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_session_binding_row import (
    IdentityRecoverySessionBindingRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_settings_binding_row import (
    IdentityRecoverySettingsBindingRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresIdentityRecoveryEvidenceWriter(IdentityRecoveryEvidenceWriter):
    """Keep native associations and checkpoints on the request's coordinated session."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
    ) -> None:
        self._session = session
        self._installation_id = installation_id
        self._authority = authority

    @override
    async def record_admission(
        self, event: IdentityRecoveryEventDTO, operation_id: OperationId
    ) -> None:
        self._require_transaction()
        # The admission collaborator has already acquired identity and organization locks.
        await self._receipt(
            identity=event.identity,
            operation_id=operation_id,
            event_type=IdentityRecoveryEvidenceType.RECOVERY_CODE_VERIFIED,
            native_flow_id=event.flow_id.value,
            session_id=None,
            source=None,
            event_kind=event.event_kind,
        )

    @override
    async def record_settings_association(
        self, evidence: IdentityRecoverySettingsEvidenceDTO, admission: IdentityRecoveryAdmissionDTO
    ) -> None:
        self._require_transaction()
        source = evidence.source_recovery_flow_id
        await self._session.execute(
            insert(IdentityRecoverySessionBindingRow)
            .values(
                installation_id=self._installation_id.value,
                authority=self._authority.value,
                subject=evidence.identity.subject.value,
                operation_id=admission.operation_id.value,
                session_id=evidence.session_id.value,
            )
            .on_conflict_do_nothing()
        )
        stored_session = (
            await self._session.scalars(
                select(IdentityRecoverySessionBindingRow)
                .where(
                    IdentityRecoverySessionBindingRow.installation_id
                    == self._installation_id.value,
                    IdentityRecoverySessionBindingRow.authority == self._authority.value,
                    IdentityRecoverySessionBindingRow.session_id == evidence.session_id.value,
                )
                .execution_options(populate_existing=True)
            )
        ).one()
        if (stored_session.subject, stored_session.operation_id) != (
            evidence.identity.subject.value,
            admission.operation_id.value,
        ):
            raise ConflictError("The native session binding conflicts.")
        await self._session.execute(
            insert(IdentityRecoverySettingsBindingRow)
            .values(
                installation_id=self._installation_id.value,
                authority=self._authority.value,
                subject=evidence.identity.subject.value,
                operation_id=admission.operation_id.value,
                settings_flow_id=evidence.settings_flow_id.value,
                session_id=evidence.session_id.value,
                source_recovery_flow_id=None if source is None else source.value,
            )
            .on_conflict_do_nothing()
        )
        stored = (
            await self._session.scalars(
                select(IdentityRecoverySettingsBindingRow)
                .where(
                    IdentityRecoverySettingsBindingRow.installation_id
                    == self._installation_id.value,
                    IdentityRecoverySettingsBindingRow.authority == self._authority.value,
                    IdentityRecoverySettingsBindingRow.settings_flow_id
                    == evidence.settings_flow_id.value,
                )
                .execution_options(populate_existing=True)
            )
        ).one()
        if (
            stored.subject,
            stored.operation_id,
            stored.session_id,
            stored.source_recovery_flow_id,
        ) != (
            evidence.identity.subject.value,
            admission.operation_id.value,
            evidence.session_id.value,
            None if source is None else source.value,
        ):
            raise ConflictError("The native settings binding conflicts.")
        await self._settings_receipt(
            evidence, admission, IdentityRecoveryEvidenceType.SETTINGS_FLOW_ASSOCIATED
        )

    @override
    async def record_password_saved(
        self, evidence: IdentityRecoverySettingsEvidenceDTO, admission: IdentityRecoveryAdmissionDTO
    ) -> datetime:
        self._require_transaction()
        receipt = await self._settings_receipt(
            evidence, admission, IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED
        )
        return receipt.recorded_at

    @override
    async def ensure_initial_cleanup_handoff(
        self,
        evidence: IdentityRecoverySettingsEvidenceDTO,
        admission: IdentityRecoveryAdmissionDTO,
        *,
        budget: IdentityRecoveryCleanupRunBudget,
    ) -> None:
        self._require_transaction()
        receipt = await self._session.scalar(
            select(IdentityRecoveryEvidenceReceiptRow)
            .where(
                IdentityRecoveryEvidenceReceiptRow.installation_id == self._installation_id.value,
                IdentityRecoveryEvidenceReceiptRow.authority == self._authority.value,
                IdentityRecoveryEvidenceReceiptRow.subject == evidence.identity.subject.value,
                IdentityRecoveryEvidenceReceiptRow.operation_id == admission.operation_id.value,
                IdentityRecoveryEvidenceReceiptRow.event_type
                == IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED,
                IdentityRecoveryEvidenceReceiptRow.native_flow_id
                == evidence.settings_flow_id.value,
            )
            .execution_options(populate_existing=True)
        )
        if receipt is None or budget.started_at != receipt.recorded_at:
            raise RuntimeError("The cleanup budget requires its stored password evidence.")
        created = await self._session.scalar(
            insert(IdentityRecoveryCleanupJobRow)
            .values(
                installation_id=self._installation_id.value,
                authority=self._authority.value,
                subject=evidence.identity.subject.value,
                operation_id=admission.operation_id.value,
                evidence_receipt_id=receipt.id,
                eligible_at=budget.started_at,
            )
            .on_conflict_do_nothing()
            .returning(IdentityRecoveryCleanupJobRow.operation_id)
        )
        if created is not None:
            await self._session.execute(
                insert(IdentityRecoveryCleanupRunRow).values(
                    id=uuid4(),
                    operation_id=admission.operation_id.value,
                    authorization_source=IdentityRecoveryRunSource.KRATOS_EVIDENCE,
                    authorized_at=budget.started_at,
                    next_attempt_at=budget.started_at,
                    deadline=budget.deadline,
                    max_attempts=budget.max_attempts,
                )
            )

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Recovery evidence persistence requires an active transaction.")

    async def _settings_receipt(
        self,
        evidence: IdentityRecoverySettingsEvidenceDTO,
        admission: IdentityRecoveryAdmissionDTO,
        kind: IdentityRecoveryEvidenceType,
    ) -> IdentityRecoveryEvidenceReceiptRow:
        return await self._receipt(
            identity=evidence.identity,
            operation_id=admission.operation_id,
            event_type=kind,
            native_flow_id=evidence.settings_flow_id.value,
            session_id=evidence.session_id.value,
            source=None
            if evidence.source_recovery_flow_id is None
            else evidence.source_recovery_flow_id.value,
            event_kind=None,
        )

    async def _receipt(
        self,
        *,
        identity: VerifiedHumanIdentityDTO,
        operation_id: OperationId,
        event_type: IdentityRecoveryEvidenceType,
        native_flow_id: UUID,
        session_id: UUID | None,
        source: UUID | None,
        event_kind: IdentityRecoveryEventKind | None,
    ) -> IdentityRecoveryEvidenceReceiptRow:
        await self._session.execute(
            insert(IdentityRecoveryEvidenceReceiptRow)
            .values(
                id=uuid4(),
                installation_id=self._installation_id.value,
                authority=self._authority.value,
                subject=identity.subject.value,
                operation_id=operation_id.value,
                event_type=event_type,
                native_flow_id=native_flow_id,
                session_id=session_id,
                source_recovery_flow_id=source,
                event_kind=event_kind,
            )
            .on_conflict_do_nothing()
        )
        stored = (
            await self._session.scalars(
                select(IdentityRecoveryEvidenceReceiptRow)
                .where(
                    IdentityRecoveryEvidenceReceiptRow.installation_id
                    == self._installation_id.value,
                    IdentityRecoveryEvidenceReceiptRow.authority == self._authority.value,
                    IdentityRecoveryEvidenceReceiptRow.event_type == event_type.value,
                    IdentityRecoveryEvidenceReceiptRow.native_flow_id == native_flow_id,
                )
                .execution_options(populate_existing=True)
            )
        ).one()
        if (
            stored.subject,
            stored.operation_id,
            stored.session_id,
            stored.source_recovery_flow_id,
            stored.event_kind,
        ) != (identity.subject.value, operation_id.value, session_id, source, event_kind):
            raise ConflictError("The native event was already recorded with different meaning.")
        return stored
