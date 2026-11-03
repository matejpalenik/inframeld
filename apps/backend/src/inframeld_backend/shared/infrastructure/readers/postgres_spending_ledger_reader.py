import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from typing import override
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Integer,
    Nullable,
    Numeric,
    and_,
    case,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_result_dto import (
    ProjectSpendingPolicyResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO
from inframeld_backend.shared.application.dtos.spending_evidence_resolution_dto import (
    SpendingEvidenceResolutionDTO,
)
from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.dtos.spending_projection_dto import SpendingProjectionDTO
from inframeld_backend.shared.application.dtos.spending_totals_dto import SpendingTotalsDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.spending_ledger_reader import (
    SpendingLedgerReader,
)
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount
from inframeld_backend.shared.infrastructure.mappers.postgres_spending_mapper import (
    PostgresSpendingMapper,
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


class PostgresSpendingLedgerReader(SpendingLedgerReader):
    """Read scoped accounting in the caller transaction without cached balances or commits."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def _stage(self) -> AsyncGenerator[None]:
        if not self._session.is_active:
            raise RuntimeError("Spending reads require an active caller session.")
        try:
            async with asyncio.timeout(5):
                yield
        except TimeoutError:
            raise DependencyUnavailableError(
                "Spending read exceeded its database deadline."
            ) from None

    @override
    async def find_call(
        self, *, organization_id: OrganizationId, project_id: ProjectId, call_id: ModelCallId
    ) -> SpendingCallRecordDTO | None:
        async with self._stage():
            row = (
                (
                    await self._session.execute(
                        select(ModelCallAccountingRow, SpendingOperationRow)
                        .join(
                            SpendingOperationRow,
                            and_(
                                SpendingOperationRow.operation_id
                                == ModelCallAccountingRow.operation_id,
                                SpendingOperationRow.organization_id
                                == ModelCallAccountingRow.organization_id,
                                SpendingOperationRow.project_id
                                == ModelCallAccountingRow.project_id,
                            ),
                        )
                        .where(
                            ModelCallAccountingRow.call_id == call_id.value,
                            ModelCallAccountingRow.organization_id == organization_id.value,
                            ModelCallAccountingRow.project_id == project_id.value,
                        )
                        .execution_options(populate_existing=True)
                    )
                )
                .tuples()
                .one_or_none()
            )
            return None if row is None else PostgresSpendingMapper.to_call(row[0], row[1])

    @override
    async def lock_project_policy(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectSpendingPolicyDTO:
        if not self._session.in_transaction():
            raise RuntimeError("Accounting coordination requires the caller's active transaction.")
        async with self._stage():
            row = (
                (
                    await self._session.execute(
                        select(
                            ProjectSpendingPolicyRow,
                            func.clock_timestamp(type_=DateTime(timezone=True)),
                        )
                        .where(
                            ProjectSpendingPolicyRow.project_id == project_id.value,
                            ProjectSpendingPolicyRow.organization_id == organization_id.value,
                        )
                        .with_for_update(of=ProjectSpendingPolicyRow)
                        .execution_options(populate_existing=True)
                    )
                )
                .tuples()
                .one_or_none()
            )
            if row is None:
                raise DependencyUnavailableError(
                    "The scoped accounting coordination root is missing."
                )
            return PostgresSpendingMapper.to_policy(row[0], row[1])

    @override
    async def project_totals(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        period: SpendingPeriod,
        exclude_call_id: ModelCallId | None = None,
    ) -> SpendingTotalsDTO:
        async with self._stage():
            predicates = [
                ModelCallAccountingRow.organization_id == organization_id.value,
                ModelCallAccountingRow.project_id == project_id.value,
                ModelCallAccountingRow.period_year == period.year,
                ModelCallAccountingRow.period_month == period.month,
            ]
            if exclude_call_id is not None:
                predicates.append(ModelCallAccountingRow.call_id != exclude_call_id.value)
            return await self._totals(predicates)

    @override
    async def operation_totals(
        self, *, record: SpendingCallRecordDTO, exclude_call_id: ModelCallId | None = None
    ) -> SpendingTotalsDTO:
        async with self._stage():
            predicates = [
                ModelCallAccountingRow.organization_id == record.authority.organization_id.value,
                ModelCallAccountingRow.project_id == record.authority.project_id.value,
                ModelCallAccountingRow.operation_id == record.operation_id.value,
            ]
            if exclude_call_id is not None:
                predicates.append(ModelCallAccountingRow.call_id != exclude_call_id.value)
            return await self._totals(predicates)

    async def _totals(self, predicates: list[ColumnElement[bool]]) -> SpendingTotalsDTO:
        settled, held, unknown = self._totals_columns()
        result = (
            (
                await self._session.execute(
                    select(settled, held, unknown)
                    .select_from(ModelCallAccountingRow)
                    .where(*predicates)
                )
            )
            .tuples()
            .one()
        )
        return SpendingTotalsDTO(UsdAmount(result[0]), UsdAmount(result[1]), result[2])

    @staticmethod
    def _totals_columns() -> tuple[
        ColumnElement[Decimal], ColumnElement[Decimal], ColumnElement[int]
    ]:
        zero = literal(Decimal("0"), Numeric())
        settled = func.coalesce(
            func.sum(
                case(
                    (
                        ModelCallAccountingRow.state == SpendingCallState.SETTLED.value,
                        ModelCallAccountingRow.settled_amount,
                    ),
                    else_=zero,
                ),
                type_=Numeric(),
            ),
            zero,
            type_=Numeric(),
        )
        active = ModelCallAccountingRow.state.not_in(
            (SpendingCallState.SETTLED.value, SpendingCallState.RELEASED.value)
        )
        held = func.coalesce(
            func.sum(
                case((active, ModelCallAccountingRow.hold_amount), else_=zero), type_=Numeric()
            ),
            zero,
            type_=Numeric(),
        )
        pending = (
            exists()
            .where(
                ModelCallAccountingEvidenceRow.call_id == ModelCallAccountingRow.call_id,
                ModelCallAccountingEvidenceRow.organization_id
                == ModelCallAccountingRow.organization_id,
                ModelCallAccountingEvidenceRow.project_id == ModelCallAccountingRow.project_id,
                ModelCallAccountingEvidenceRow.was_pending.is_(True),
                ModelCallAccountingEvidenceRow.resolved_by_evidence_id.is_(None),
            )
            .correlate(ModelCallAccountingRow)
        )
        incomplete = or_(
            pending,
            and_(active, ModelCallAccountingRow.hold_amount.is_(None)),
            and_(
                ModelCallAccountingRow.state == SpendingCallState.SETTLED.value,
                ModelCallAccountingRow.settled_amount.is_(None),
            ),
            ModelCallAccountingRow.state.not_in(tuple(state.value for state in SpendingCallState)),
        )
        unknown = func.coalesce(
            func.sum(
                case((and_(ModelCallAccountingRow.call_id.is_not(None), incomplete), 1), else_=0),
                type_=Integer(),
            ),
            0,
            type_=Integer(),
        )
        return settled, held, unknown

    @override
    async def observation(
        self, *, record: SpendingCallRecordDTO, evidence_id: UUID
    ) -> tuple[SpendingObservationDTO, SpendingCallRecordDTO | None, bool] | None:
        async with self._stage():
            row = await self._evidence(record, evidence_id)
            return None if row is None else PostgresSpendingMapper.to_observation(row, record)

    @override
    async def resolution(
        self, *, record: SpendingCallRecordDTO, pending_evidence_id: UUID
    ) -> SpendingEvidenceResolutionDTO | None:
        async with self._stage():
            row = await self._evidence(record, pending_evidence_id)
            return None if row is None else PostgresSpendingMapper.to_resolution(row, record)

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
            .execution_options(populate_existing=True)
        )

    @override
    async def project_projection(
        self, *, organization_id: OrganizationId, project_id: ProjectId, period: SpendingPeriod
    ) -> SpendingProjectionDTO:
        async with self._stage():
            settled, held, unknown = self._totals_columns()
            remaining = Nullable(
                case(
                    (unknown == 0, ProjectSpendingPolicyRow.monthly_limit - settled - held),
                    else_=None,
                )
            )
            # Policy, period amounts and unresolved markers share this single SQL
            # statement snapshot. Inspection never creates a coordination row.
            result = (
                (
                    await self._session.execute(
                        select(
                            Nullable(ProjectSpendingPolicyRow.revision),
                            Nullable(ProjectSpendingPolicyRow.monthly_limit),
                            settled,
                            held,
                            unknown,
                            remaining,
                            func.count(ModelCallAccountingRow.call_id),
                            func.clock_timestamp(type_=DateTime(timezone=True)),
                        )
                        .select_from(ProjectRow)
                        .outerjoin(
                            ProjectSpendingPolicyRow,
                            and_(
                                ProjectSpendingPolicyRow.project_id == ProjectRow.id,
                                ProjectSpendingPolicyRow.organization_id
                                == ProjectRow.organization_id,
                            ),
                        )
                        .outerjoin(
                            ModelCallAccountingRow,
                            and_(
                                ModelCallAccountingRow.project_id == ProjectRow.id,
                                ModelCallAccountingRow.organization_id
                                == ProjectRow.organization_id,
                                ModelCallAccountingRow.period_year == period.year,
                                ModelCallAccountingRow.period_month == period.month,
                            ),
                        )
                        .where(
                            ProjectRow.id == project_id.value,
                            ProjectRow.organization_id == organization_id.value,
                        )
                        .group_by(
                            ProjectSpendingPolicyRow.revision,
                            ProjectSpendingPolicyRow.monthly_limit,
                        )
                    )
                )
                .tuples()
                .one_or_none()
            )
            if result is None:
                raise ResourceNotFoundError()
            revision, limit, charged, reserved, unquantified, available, count, observed_at = result
            if revision is None and count:
                raise DependencyUnavailableError("Accounting records have no coordination root.")
            policy = ProjectSpendingPolicyDTO(
                organization_id,
                project_id,
                0 if revision is None else revision,
                PostgresSpendingMapper.amount(limit),
                observed_at,
            )
            return SpendingProjectionDTO(
                policy,
                period,
                SpendingTotalsDTO(UsdAmount(charged), UsdAmount(reserved), unquantified),
                PostgresSpendingMapper.amount(available),
            )

    @override
    async def policy_result(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_id: PrincipalId,
        completion: CompletedSynchronousOperationDTO,
    ) -> ProjectSpendingPolicyResultDTO:
        async with self._stage():
            if completion.replay_kind is not OperationReplayKind.SAFE_RESULT:
                raise ConflictError("Policy replay requires a safe synchronous result.")
            row = await self._session.scalar(
                select(ProjectSpendingPolicyOperationResultRow)
                .where(
                    ProjectSpendingPolicyOperationResultRow.operation_id
                    == completion.operation_id.value,
                    ProjectSpendingPolicyOperationResultRow.organization_id
                    == organization_id.value,
                    ProjectSpendingPolicyOperationResultRow.project_id == project_id.value,
                    ProjectSpendingPolicyOperationResultRow.actor_id == actor_id.value,
                )
                .execution_options(populate_existing=True)
            )
            if row is None:
                raise ResourceNotFoundError()
            policy = ProjectSpendingPolicyDTO(
                organization_id,
                project_id,
                row.revision,
                PostgresSpendingMapper.amount(row.monthly_limit),
                row.observed_at,
            )
            return ProjectSpendingPolicyResultDTO(policy, completion, row.changed)
