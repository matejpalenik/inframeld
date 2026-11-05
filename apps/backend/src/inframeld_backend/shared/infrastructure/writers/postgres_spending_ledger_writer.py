import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import override
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_context_dto import (
    SpendingCallContextDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO
from inframeld_backend.shared.application.dtos.spending_evidence_resolution_dto import (
    SpendingEvidenceResolutionDTO,
)
from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.spending_ledger_writer import (
    SpendingLedgerWriter,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount
from inframeld_backend.shared.infrastructure.mappers.postgres_spending_mapper import (
    PostgresSpendingMapper,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_evidence_row import (
    ModelCallAccountingEvidenceRow,
)
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_row import (
    ModelCallAccountingRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_operation_result_row import (
    ProjectSpendingPolicyOperationResultRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_row import (
    ProjectSpendingPolicyRow,
)
from inframeld_backend.shared.infrastructure.rows.spending_operation_row import SpendingOperationRow


class PostgresSpendingLedgerWriter(SpendingLedgerWriter):
    """Persist checked transitions under Project, operation and call coordination, never committing."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def _stage(self) -> AsyncGenerator[None]:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Spending writes require the caller's active transaction.")
        try:
            async with asyncio.timeout(5):
                yield
        except TimeoutError:
            raise DependencyUnavailableError(
                "Spending write exceeded its database deadline."
            ) from None

    @staticmethod
    def _value(amount: UsdAmount | None) -> Decimal | None:
        return None if amount is None else amount.value

    @override
    async def ensure_project_account(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> None:
        async with self._stage():
            project = await self._session.scalar(
                select(ProjectRow.id).where(
                    ProjectRow.id == project_id.value,
                    ProjectRow.organization_id == organization_id.value,
                )
            )
            if project is None:
                raise ResourceNotFoundError()
            await self._session.execute(
                insert(ProjectSpendingPolicyRow)
                .values(
                    project_id=project_id.value,
                    organization_id=organization_id.value,
                    revision=0,
                    monthly_limit=None,
                )
                .on_conflict_do_nothing(index_elements=[ProjectSpendingPolicyRow.project_id])
            )
            # The caller follows with the scoped FOR UPDATE reread. This insert
            # never replaces policy and never retries the owning transaction.

    @override
    async def ensure_operation(
        self, *, call: SpendingCallContextDTO, operation_limit: UsdAmount | None
    ) -> None:
        async with self._stage():
            authority = call.authority
            binding = authority.human_binding
            await self._session.execute(
                insert(SpendingOperationRow)
                .values(
                    operation_id=call.operation_id.value,
                    organization_id=authority.organization_id.value,
                    project_id=authority.project_id.value,
                    job_id=call.attempt.job_id.value,
                    installation_id=authority.installation_id.value,
                    principal_id=authority.principal_id.value,
                    principal_kind=authority.principal_kind.value,
                    action_id=authority.action_id.value,
                    operation_limit=self._value(operation_limit),
                    human_authority=None if binding is None else binding.identity.authority.value,
                    human_subject=None if binding is None else binding.identity.subject.value,
                    human_version=None if binding is None else binding.version.value,
                )
                .on_conflict_do_nothing(index_elements=[SpendingOperationRow.operation_id])
            )
            stored = await self._operation(call.operation_id)
            self._require_operation_binding(stored, call.attempt.job_id, authority, operation_limit)

    async def _operation(self, operation_id: OperationId) -> SpendingOperationRow:
        row = await self._session.scalar(
            select(SpendingOperationRow)
            .where(SpendingOperationRow.operation_id == operation_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ConflictError("Original spending operation is missing.")
        return row

    @staticmethod
    def _require_operation_binding(
        row: SpendingOperationRow,
        job_id: JobId,
        authority: AdmittedWorkAuthorityDTO,
        operation_limit: UsdAmount | None,
    ) -> None:
        binding = authority.human_binding
        stored = (
            row.job_id,
            row.organization_id,
            row.project_id,
            row.installation_id,
            row.principal_id,
            row.principal_kind,
            row.action_id,
            row.operation_limit,
            row.human_authority,
            row.human_subject,
            row.human_version,
        )
        expected = (
            job_id.value,
            authority.organization_id.value,
            authority.project_id.value,
            authority.installation_id.value,
            authority.principal_id.value,
            authority.principal_kind.value,
            authority.action_id.value,
            PostgresSpendingLedgerWriter._value(operation_limit),
            None if binding is None else binding.identity.authority.value,
            None if binding is None else binding.identity.subject.value,
            None if binding is None else binding.version.value,
        )
        if stored != expected:
            raise ConflictError("Original spending operation binding changed.")

    @override
    async def insert_call(self, record: SpendingCallRecordDTO) -> None:
        async with self._stage():
            operation = await self._operation(record.operation_id)
            self._require_operation_binding(
                operation, record.job_id, record.authority, record.operation_limit
            )
            if record.revision != 0:
                raise ConflictError("A new call must start at its original revision.")
            self._session.add(
                ModelCallAccountingRow(
                    call_id=record.call_id.value,
                    organization_id=record.authority.organization_id.value,
                    project_id=record.authority.project_id.value,
                    operation_id=record.operation_id.value,
                    meaning_fingerprint=record.meaning_fingerprint.value,
                    period_year=record.period.year,
                    period_month=record.period.month,
                    basis=PostgresSpendingMapper.basis_values(record.basis),
                    reserved_amount=self._value(record.reserved_amount),
                    hold_amount=self._value(record.hold_amount),
                    settled_amount=self._value(record.settled_amount),
                    state=record.state.value,
                    revision=record.revision,
                    reservation_policy_revision=record.reservation_policy_revision,
                    approved_policy_revision=record.approved_policy_revision,
                )
            )
            try:
                await self._session.flush()
            except IntegrityError:
                raise ConflictError(
                    "The original call identity already exists or is invalid."
                ) from None

    async def _locked_call(
        self, record: SpendingCallRecordDTO
    ) -> tuple[ModelCallAccountingRow, SpendingCallRecordDTO]:
        operation = await self._operation(record.operation_id)
        self._require_operation_binding(
            operation, record.job_id, record.authority, record.operation_limit
        )
        row = await self._session.scalar(
            select(ModelCallAccountingRow)
            .where(
                ModelCallAccountingRow.call_id == record.call_id.value,
                ModelCallAccountingRow.organization_id == record.authority.organization_id.value,
                ModelCallAccountingRow.project_id == record.authority.project_id.value,
                ModelCallAccountingRow.operation_id == record.operation_id.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ResourceNotFoundError()
        stored = PostgresSpendingMapper.to_call(row, operation)
        self._require_immutable_call(stored, record)
        return row, stored

    @staticmethod
    def _require_immutable_call(
        original: SpendingCallRecordDTO, candidate: SpendingCallRecordDTO
    ) -> None:
        if (
            original.call_id,
            original.operation_id,
            original.authority,
            original.job_id,
            original.meaning_fingerprint,
            original.period,
            original.operation_limit,
            original.basis,
            original.reserved_amount,
            original.reservation_policy_revision,
        ) != (
            candidate.call_id,
            candidate.operation_id,
            candidate.authority,
            candidate.job_id,
            candidate.meaning_fingerprint,
            candidate.period,
            candidate.operation_limit,
            candidate.basis,
            candidate.reserved_amount,
            candidate.reservation_policy_revision,
        ):
            raise ConflictError("Original call attribution or reservation basis changed.")

    @override
    async def save_call(self, record: SpendingCallRecordDTO, *, expected_revision: int) -> None:
        async with self._stage():
            row, _ = await self._locked_call(record)
            if row.revision != expected_revision or record.revision != expected_revision + 1:
                raise StaleRevisionError()
            changed = await self._session.scalar(
                update(ModelCallAccountingRow)
                .where(
                    ModelCallAccountingRow.call_id == record.call_id.value,
                    ModelCallAccountingRow.organization_id
                    == record.authority.organization_id.value,
                    ModelCallAccountingRow.project_id == record.authority.project_id.value,
                    ModelCallAccountingRow.revision == expected_revision,
                )
                .values(
                    state=record.state.value,
                    revision=record.revision,
                    hold_amount=self._value(record.hold_amount),
                    settled_amount=self._value(record.settled_amount),
                    approved_policy_revision=record.approved_policy_revision,
                )
                .returning(ModelCallAccountingRow.call_id)
                .execution_options(synchronize_session=False)
            )
            if changed is None:
                raise StaleRevisionError()

    async def _evidence(
        self, record: SpendingCallRecordDTO, evidence_id: UUID
    ) -> ModelCallAccountingEvidenceRow | None:
        return await self._session.scalar(
            select(ModelCallAccountingEvidenceRow)
            .where(
                ModelCallAccountingEvidenceRow.call_id == record.call_id.value,
                ModelCallAccountingEvidenceRow.evidence_id == evidence_id,
                ModelCallAccountingEvidenceRow.organization_id
                == record.authority.organization_id.value,
                ModelCallAccountingEvidenceRow.project_id == record.authority.project_id.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    @override
    async def record_observation(
        self,
        *,
        record: SpendingCallRecordDTO,
        observation: SpendingObservationDTO,
        applied_result: SpendingCallRecordDTO | None,
    ) -> None:
        async with self._stage():
            _, current = await self._locked_call(record)
            if observation.call_id != record.call_id:
                raise ConflictError("Evidence changed its original call.")
            existing = await self._evidence(record, observation.evidence_id)
            if existing is not None:
                saved, applied, _ = PostgresSpendingMapper.to_observation(existing, record)
                if saved != observation or (
                    applied_result is not None and applied != applied_result
                ):
                    raise ConflictError("Evidence identity changed meaning or financial receipt.")
                return
            if current.revision != record.revision:
                raise StaleRevisionError()
            if applied_result is not None:
                self._require_immutable_call(record, applied_result)
                if applied_result.revision != record.revision + 1:
                    raise StaleRevisionError()
            self._session.add(
                ModelCallAccountingEvidenceRow(
                    call_id=record.call_id.value,
                    evidence_id=observation.evidence_id,
                    organization_id=record.authority.organization_id.value,
                    project_id=record.authority.project_id.value,
                    kind=observation.kind,
                    observed_at=observation.observed_at,
                    source_reference=observation.source_reference,
                    usage=PostgresSpendingMapper.usage_values(observation.usage),
                    charge=observation.charge,
                    was_pending=applied_result is None,
                    applied_state=None if applied_result is None else applied_result.state.value,
                    applied_hold_amount=None
                    if applied_result is None
                    else self._value(applied_result.hold_amount),
                    applied_settled_amount=None
                    if applied_result is None
                    else self._value(applied_result.settled_amount),
                    applied_revision=None if applied_result is None else applied_result.revision,
                    applied_approved_policy_revision=None
                    if applied_result is None
                    else applied_result.approved_policy_revision,
                )
            )
            await self._session.flush()

    @override
    async def mark_observation_applied(
        self, *, record: SpendingCallRecordDTO, evidence_id: UUID, result: SpendingCallRecordDTO
    ) -> None:
        async with self._stage():
            _, current = await self._locked_call(record)
            if current != result:
                raise StaleRevisionError()
            row = await self._evidence(record, evidence_id)
            if row is None:
                raise ResourceNotFoundError()
            _, original, _ = PostgresSpendingMapper.to_observation(row, record)
            if original is not None:
                if original != result:
                    raise ConflictError("Original financial receipt cannot be replaced.")
                return
            row.applied_state = result.state.value
            row.applied_hold_amount = self._value(result.hold_amount)
            row.applied_settled_amount = self._value(result.settled_amount)
            row.applied_revision = result.revision
            row.applied_approved_policy_revision = result.approved_policy_revision
            # Financial application never clears this evidence's pending marker.
            await self._session.flush()

    @override
    async def record_resolution(
        self, *, record: SpendingCallRecordDTO, resolution: SpendingEvidenceResolutionDTO
    ) -> None:
        async with self._stage():
            _, current = await self._locked_call(record)
            pending = await self._evidence(record, resolution.pending_evidence_id)
            if pending is None:
                raise ResourceNotFoundError()
            original = PostgresSpendingMapper.to_resolution(pending, record)
            if original is not None:
                if original != resolution:
                    raise ConflictError("Original evidence resolution cannot be replaced.")
                return
            if not pending.was_pending:
                raise ConflictError("The selected evidence has no pending marker.")
            if current != resolution.result:
                raise StaleRevisionError()
            if await self._evidence(record, resolution.authoritative_evidence_id) is None:
                raise ResourceNotFoundError()
            pending.resolved_by_evidence_id = resolution.authoritative_evidence_id
            pending.resolution_state = resolution.result.state.value
            pending.resolution_hold_amount = self._value(resolution.result.hold_amount)
            pending.resolution_settled_amount = self._value(resolution.result.settled_amount)
            pending.resolution_revision = resolution.result.revision
            pending.resolution_approved_policy_revision = resolution.result.approved_policy_revision
            await self._session.flush()

    @override
    async def save_correction_audit(
        self,
        *,
        actor_id: PrincipalId,
        resolution: SpendingEvidenceResolutionDTO,
        previous_revision: int,
    ) -> None:
        async with self._stage():
            record = resolution.result
            await self._require_human_actor(actor_id, record.authority.organization_id)
            self._session.add(
                AccessAuditEventRow(
                    id=uuid4(),
                    organization_id=record.authority.organization_id.value,
                    actor_kind=PrincipalKind.HUMAN.value,
                    actor_principal_id=actor_id.value,
                    event_type="spending_evidence_resolved",
                    target_kind="model-call",
                    target_id=record.call_id.value,
                    project_id=record.authority.project_id.value,
                    action=ProjectAction.MANAGE_BUDGET.value,
                    before_values={"call_revision": previous_revision},
                    after_values={
                        "call_revision": record.revision,
                        "pending_evidence_id": str(resolution.pending_evidence_id),
                        "authoritative_evidence_id": str(resolution.authoritative_evidence_id),
                    },
                )
            )
            await self._session.flush()

    async def _require_human_actor(
        self, actor_id: PrincipalId, organization_id: OrganizationId
    ) -> None:
        actor = await self._session.scalar(
            select(PrincipalRow.id).where(
                PrincipalRow.id == actor_id.value,
                PrincipalRow.organization_id == organization_id.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
            )
        )
        if actor is None:
            raise ConflictError("Budget audit actor has inconsistent scope or kind.")

    @override
    async def change_policy(
        self,
        *,
        policy: ProjectSpendingPolicyDTO,
        expected_revision: int,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        async with self._stage():
            await self._require_human_actor(actor_id, policy.organization_id)
            row = await self._session.scalar(
                select(ProjectSpendingPolicyRow)
                .where(
                    ProjectSpendingPolicyRow.project_id == policy.project_id.value,
                    ProjectSpendingPolicyRow.organization_id == policy.organization_id.value,
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if (
                row is None
                or row.revision != expected_revision
                or policy.revision != expected_revision + 1
            ):
                raise StaleRevisionError()
            old_limit = row.monthly_limit
            changed = await self._session.scalar(
                update(ProjectSpendingPolicyRow)
                .where(
                    ProjectSpendingPolicyRow.project_id == policy.project_id.value,
                    ProjectSpendingPolicyRow.organization_id == policy.organization_id.value,
                    ProjectSpendingPolicyRow.revision == expected_revision,
                )
                .values(revision=policy.revision, monthly_limit=self._value(policy.monthly_limit))
                .returning(ProjectSpendingPolicyRow.project_id)
                .execution_options(synchronize_session=False)
            )
            if changed is None:
                raise StaleRevisionError()
            self._session.add(
                AccessAuditEventRow(
                    id=uuid4(),
                    organization_id=policy.organization_id.value,
                    actor_kind=PrincipalKind.HUMAN.value,
                    actor_principal_id=actor_id.value,
                    event_type="project_spending_policy_changed",
                    target_kind="project",
                    target_id=policy.project_id.value,
                    project_id=policy.project_id.value,
                    action=ProjectAction.MANAGE_BUDGET.value,
                    correlation_id=operation_id.value,
                    before_values={
                        "revision": expected_revision,
                        "monthly_limit": None if old_limit is None else str(old_limit),
                    },
                    after_values={
                        "revision": policy.revision,
                        "monthly_limit": None
                        if policy.monthly_limit is None
                        else str(policy.monthly_limit.value),
                    },
                )
            )
            await self._session.flush()

    @override
    async def save_policy_result(
        self,
        *,
        policy: ProjectSpendingPolicyDTO,
        actor_id: PrincipalId,
        operation_id: OperationId,
        changed: bool,
    ) -> None:
        async with self._stage():
            operation = await self._session.scalar(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.operation_id == operation_id.value,
                    IdempotencyReservationRow.principal_id == actor_id.value,
                    IdempotencyReservationRow.organization_id == policy.organization_id.value,
                    IdempotencyReservationRow.project_id == policy.project_id.value,
                    IdempotencyReservationRow.lookup_authority_family
                    == OperationLookupAuthorityFamily.PROJECT_ACTION_USE.value,
                    IdempotencyReservationRow.lookup_action_id == ProjectAction.MANAGE_BUDGET.value,
                )
            )
            if operation is None:
                raise ConflictError("Policy result has no matching original replay reservation.")
            self._session.add(
                ProjectSpendingPolicyOperationResultRow(
                    operation_id=operation_id.value,
                    organization_id=policy.organization_id.value,
                    project_id=policy.project_id.value,
                    actor_id=actor_id.value,
                    revision=policy.revision,
                    monthly_limit=self._value(policy.monthly_limit),
                    observed_at=policy.observed_at,
                    changed=changed,
                )
            )
            await self._session.flush()
