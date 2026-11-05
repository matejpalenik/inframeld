from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from typing import override
from uuid import UUID

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.access.application.protocols.project_budget_authorizer import (
    ProjectBudgetAuthorizer,
)
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)
from inframeld_backend.shared.application.dtos.spending_accounting_result_dto import (
    SpendingAccountingResultDTO,
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
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.errors.spending_errors import (
    IncompleteSpendingFactsError,
    SpendingLimitExceededError,
)
from inframeld_backend.shared.application.protocols.job_ownership import JobOwnership
from inframeld_backend.shared.application.protocols.spending_accountant import SpendingAccountant
from inframeld_backend.shared.application.protocols.spending_ledger_reader import (
    SpendingLedgerReader,
)
from inframeld_backend.shared.application.protocols.spending_ledger_writer import (
    SpendingLedgerWriter,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.domain.policies.spending_allowance_policy import (
    SpendingAllowancePolicy,
)
from inframeld_backend.shared.domain.policy_inputs.spending_allowance_policy_input import (
    SpendingAllowancePolicyInput,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


class SpendingAccountingService(SpendingAccountant):
    """Coordinate original job-bound accounting through short owning transactions."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        admitted_work_authorizer: AdmittedWorkAuthorizer,
        job_ownership: JobOwnership,
        spending_ledger_reader: SpendingLedgerReader,
        spending_ledger_writer: SpendingLedgerWriter,
        project_budget_authorizer: ProjectBudgetAuthorizer,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._admitted_work_authorizer = admitted_work_authorizer
        self._job_ownership = job_ownership
        self._spending_ledger_reader = spending_ledger_reader
        self._spending_ledger_writer = spending_ledger_writer
        self._project_budget_authorizer = project_budget_authorizer

    @override
    async def reserve(
        self,
        *,
        call: SpendingCallContextDTO,
        basis: CapturedSpendingBasisDTO | None,
        operation_limit: UsdAmount | None,
    ) -> SpendingAccountingResultDTO:
        if operation_limit is not None and operation_limit.value < 0:
            raise ValueError("An operation spending limit cannot be negative.")
        async with self._transaction_manager.begin():
            await self._admitted_work_authorizer.require_current(call.authority)
            current = await self._job_ownership.require_current(call.attempt)
            if current.cancel_requested:
                raise JobStoppedError("Canceled work cannot reserve a new call.")
            policy = await self._lock_account(call)
            await self._spending_ledger_writer.ensure_operation(
                call=call, operation_limit=operation_limit
            )
            existing = await self._find_call(call)
            if existing is not None:
                self._require_binding(existing, call)
                if existing.basis != basis or existing.operation_limit != operation_limit:
                    raise ConflictError("Original call reservation meaning changed.")
                return SpendingAccountingResultDTO(existing, recovered=True)
            amount = self._cost(basis, None if basis is None else basis.maximum_usage)
            record = SpendingCallRecordDTO(
                call_id=call.call_id,
                operation_id=call.operation_id,
                authority=call.authority,
                job_id=call.attempt.job_id,
                meaning_fingerprint=call.meaning_fingerprint,
                period=SpendingPeriod.from_instant(policy.observed_at),
                operation_limit=operation_limit,
                basis=basis,
                reserved_amount=amount,
                hold_amount=amount,
                settled_amount=None,
                state=SpendingCallState.RESERVED,
                revision=0,
                reservation_policy_revision=policy.revision,
            )
            await self._require_allowance(policy, record, amount)
            await self._spending_ledger_writer.insert_call(record)
            return SpendingAccountingResultDTO(record)

    @override
    async def approve_accounting(
        self, *, call: SpendingCallContextDTO, expected_call_revision: int
    ) -> SpendingAccountingResultDTO:
        async with self._transaction_manager.begin():
            await self._admitted_work_authorizer.require_current(call.authority)
            current = await self._job_ownership.require_current(call.attempt)
            if current.cancel_requested:
                raise JobStoppedError("Canceled work cannot receive accounting approval.")
            policy = await self._lock_account(call)
            record = await self._require_call(call)
            if record.state is SpendingCallState.ACCOUNTING_APPROVED:
                return SpendingAccountingResultDTO(record, recovered=True)
            self._require_revision(record, expected_call_revision)
            if record.state is not SpendingCallState.RESERVED:
                raise ConflictError(
                    "An unresolved or completed call cannot receive accounting approval."
                )
            await self._require_allowance(policy, record, record.hold_amount, exclude_self=True)
            updated = replace(
                record,
                state=SpendingCallState.ACCOUNTING_APPROVED,
                approved_policy_revision=policy.revision,
                revision=SpendingAccountingService._next_revision(record.revision),
            )
            await self._spending_ledger_writer.save_call(updated, expected_revision=record.revision)
            return SpendingAccountingResultDTO(updated)

    @override
    async def record_observation(
        self,
        *,
        call: SpendingCallContextDTO,
        observation: SpendingObservationDTO,
        expected_call_revision: int,
    ) -> SpendingAccountingResultDTO:
        if observation.call_id != call.call_id:
            raise ConflictError("Evidence must identify the original call.")
        async with self._transaction_manager.begin():
            await self._admitted_work_authorizer.require_current(call.authority)
            await self._require_call(call)
            try:
                await self._job_ownership.require_current(call.attempt)
            except JobFenceLostError:
                # Normal return preserves this evidence in the owning transaction.
                # The accounting record and its hold remain untouched.
                await self._lock_account(call)
                record = await self._require_call(call)
                return await self._retain_pending(record, observation, expected_call_revision)
            await self._lock_account(call)
            record = await self._require_call(call)
            recovered = await self._recover_observation(record, observation)
            if recovered is not None:
                return recovered
            self._require_revision(record, expected_call_revision)
            if record.state in (SpendingCallState.SETTLED, SpendingCallState.RELEASED):
                return await self._retain_pending(record, observation, expected_call_revision)
            updated = self._apply_observation(record, observation)
            await self._spending_ledger_writer.record_observation(
                record=record, observation=observation, applied_result=updated
            )
            await self._spending_ledger_writer.save_call(updated, expected_revision=record.revision)
            return SpendingAccountingResultDTO(updated)

    @override
    async def reconcile(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        call_id: ModelCallId,
        pending_evidence_id: UUID,
        authoritative_evidence_id: UUID,
        expected_call_revision: int,
    ) -> SpendingAccountingResultDTO:
        async with self._transaction_manager.begin():
            authorization = await self._project_budget_authorizer.require_authorization(
                access=access,
                request=ProjectActionAuthorizationRequestDTO(
                    project_id, ActionId(ProjectAction.MANAGE_BUDGET.value)
                ),
            )
            if authorization.project_id != project_id:
                raise AccessDeniedError()
            await self._spending_ledger_writer.ensure_project_account(
                organization_id=authorization.organization_id, project_id=project_id
            )
            policy = await self._spending_ledger_reader.lock_project_policy(
                organization_id=authorization.organization_id, project_id=project_id
            )
            self._require_policy_scope(policy, authorization.organization_id, project_id)
            record = await self._spending_ledger_reader.find_call(
                organization_id=authorization.organization_id,
                project_id=project_id,
                call_id=call_id,
            )
            if record is None:
                raise ResourceNotFoundError()
            self._require_call_scope(record, authorization.organization_id, project_id, call_id)
            resolved = await self._resolution(record, pending_evidence_id)
            if resolved is not None:
                if resolved.authoritative_evidence_id != authoritative_evidence_id:
                    raise ConflictError("Resolution request changed its proof binding.")
                return SpendingAccountingResultDTO(resolved.result, recovered=True)
            pending = await self._evidence(record, pending_evidence_id)
            proof = await self._evidence(record, authoritative_evidence_id)
            if pending is None or proof is None:
                raise ResourceNotFoundError()
            self._require_revision(record, expected_call_revision)
            if not pending[2]:
                raise ConflictError("Selected evidence is not pending.")
            observation, applied, _ = proof
            if observation.kind == "uncertain" or (
                observation.kind == "usage" and self._cost(record.basis, observation.usage) is None
            ):
                raise IncompleteSpendingFactsError(
                    "A correction requires authoritative accounting facts."
                )
            proof_resolution = (
                None
                if pending_evidence_id == authoritative_evidence_id
                else await self._resolution(record, authoritative_evidence_id)
            )
            already_applied = applied is not None or (
                proof_resolution is not None
                and proof_resolution.authoritative_evidence_id == authoritative_evidence_id
            )
            updated = (
                replace(record, revision=SpendingAccountingService._next_revision(record.revision))
                if already_applied
                else self._apply_observation(record, observation)
            )
            await self._spending_ledger_writer.save_call(updated, expected_revision=record.revision)
            if not already_applied and authoritative_evidence_id != pending_evidence_id:
                await self._spending_ledger_writer.mark_observation_applied(
                    record=record, evidence_id=authoritative_evidence_id, result=updated
                )
            resolution = SpendingEvidenceResolutionDTO(
                pending_evidence_id, authoritative_evidence_id, updated
            )
            await self._spending_ledger_writer.record_resolution(
                record=record, resolution=resolution
            )
            await self._spending_ledger_writer.save_correction_audit(
                actor_id=access.actor_principal_id,
                resolution=resolution,
                previous_revision=record.revision,
            )
            return SpendingAccountingResultDTO(updated)

    async def _evidence(
        self, record: SpendingCallRecordDTO, evidence_id: UUID
    ) -> tuple[SpendingObservationDTO, SpendingCallRecordDTO | None, bool] | None:
        """Recover retained evidence only when it belongs to this model call."""
        retained = await self._spending_ledger_reader.observation(
            record=record, evidence_id=evidence_id
        )
        if retained is not None:
            observation, result, _ = retained
            if observation.call_id != record.call_id or observation.evidence_id != evidence_id:
                raise RuntimeError("Accounting evidence changed its scope.")
            if result is not None:
                self._require_call_scope(
                    result,
                    record.authority.organization_id,
                    record.authority.project_id,
                    record.call_id,
                )
        return retained

    async def _resolution(
        self, record: SpendingCallRecordDTO, pending_evidence_id: UUID
    ) -> SpendingEvidenceResolutionDTO | None:
        """Load a resolution bound to the original pending evidence and call."""
        resolution = await self._spending_ledger_reader.resolution(
            record=record, pending_evidence_id=pending_evidence_id
        )
        if resolution is not None:
            if resolution.pending_evidence_id != pending_evidence_id:
                raise RuntimeError("Accounting resolution changed its pending scope.")
            self._require_call_scope(
                resolution.result,
                record.authority.organization_id,
                record.authority.project_id,
                record.call_id,
            )
        return resolution

    @staticmethod
    def _require_call_scope(
        record: SpendingCallRecordDTO,
        organization_id: OrganizationId,
        project_id: ProjectId,
        call_id: ModelCallId,
    ) -> None:
        """Reject a call record that substituted a different checked spending scope."""
        if (record.authority.organization_id, record.authority.project_id, record.call_id) != (
            organization_id,
            project_id,
            call_id,
        ):
            raise RuntimeError("Accounting call changed its scope.")

    @staticmethod
    def _require_policy_scope(
        policy: ProjectSpendingPolicyDTO, organization_id: OrganizationId, project_id: ProjectId
    ) -> None:
        """Reject a budget policy returned for another Organization or Project."""
        if (policy.organization_id, policy.project_id) != (organization_id, project_id):
            raise RuntimeError("Accounting policy changed its scope.")

    async def _lock_account(self, call: SpendingCallContextDTO) -> ProjectSpendingPolicyDTO:
        """Create the Project account if necessary and lock its current spending policy."""
        scope = call.authority
        await self._spending_ledger_writer.ensure_project_account(
            organization_id=scope.organization_id, project_id=scope.project_id
        )
        policy = await self._spending_ledger_reader.lock_project_policy(
            organization_id=scope.organization_id, project_id=scope.project_id
        )
        self._require_policy_scope(policy, scope.organization_id, scope.project_id)
        return policy

    async def _find_call(self, call: SpendingCallContextDTO) -> SpendingCallRecordDTO | None:
        return await self._spending_ledger_reader.find_call(
            organization_id=call.authority.organization_id,
            project_id=call.authority.project_id,
            call_id=call.call_id,
        )

    async def _require_call(self, call: SpendingCallContextDTO) -> SpendingCallRecordDTO:
        """Require an existing call before changing its accounting state."""
        record = await self._find_call(call)
        if record is None:
            raise ResourceNotFoundError()
        self._require_binding(record, call)
        return record

    @staticmethod
    def _require_binding(record: SpendingCallRecordDTO, call: SpendingCallContextDTO) -> None:
        """Keep a model call bound to its original operation and authority."""
        if (
            record.call_id != call.call_id
            or record.operation_id != call.operation_id
            or record.authority != call.authority
            or record.job_id != call.attempt.job_id
            or record.meaning_fingerprint != call.meaning_fingerprint
        ):
            raise ConflictError("Original call binding changed.")

    @staticmethod
    def _require_revision(record: SpendingCallRecordDTO, expected_revision: int) -> None:
        """Reject stale accounting updates before changing retained evidence."""
        if (
            type(expected_revision) is not int
            or not 0 <= expected_revision <= RevisionValidation.MAX_VALUE
        ):
            raise ValueError("Accounting requires a nonnegative reviewed call revision.")
        if record.revision != expected_revision:
            raise StaleRevisionError()

    @staticmethod
    def _next_revision(revision: int) -> int:
        RevisionValidation.require(revision)
        if revision == RevisionValidation.MAX_VALUE:
            raise ConflictError("The accounting revision cannot advance.")
        return revision + 1

    async def _require_allowance(
        self,
        policy: ProjectSpendingPolicyDTO,
        record: SpendingCallRecordDTO,
        amount: UsdAmount | None,
        *,
        exclude_self: bool = False,
    ) -> None:
        """Check conservative Project and operation totals before approving a reservation.

        Excluding this call must not conceal unresolved evidence.
        """
        excluded = record.call_id if exclude_self else None
        project = await self._spending_ledger_reader.project_totals(
            organization_id=record.authority.organization_id,
            project_id=record.authority.project_id,
            period=record.period,
            exclude_call_id=excluded,
        )
        operation = await self._spending_ledger_reader.operation_totals(
            record=record, exclude_call_id=excluded
        )
        if exclude_self:
            # Excluding this call prevents double-counting its reservation, but
            # cannot hide its pending evidence from the completeness precondition.
            if policy.monthly_limit is not None:
                applicable = await self._spending_ledger_reader.project_totals(
                    organization_id=record.authority.organization_id,
                    project_id=record.authority.project_id,
                    period=record.period,
                )
                if applicable.unquantified_holds:
                    raise IncompleteSpendingFactsError("Applicable Project facts are incomplete.")
            if record.operation_limit is not None:
                applicable = await self._spending_ledger_reader.operation_totals(record=record)
                if applicable.unquantified_holds:
                    raise IncompleteSpendingFactsError("Applicable operation facts are incomplete.")
        if (
            policy.monthly_limit is not None and (project.unquantified_holds or amount is None)
        ) or (
            record.operation_limit is not None and (operation.unquantified_holds or amount is None)
        ):
            raise IncompleteSpendingFactsError(
                "Applicable spending facts lack a conservative bound."
            )
        if not SpendingAllowancePolicy.can_reserve(
            SpendingAllowancePolicyInput(
                project_limit=policy.monthly_limit,
                project_settled=project.settled,
                project_held=project.held,
                operation_limit=record.operation_limit,
                operation_settled=operation.settled,
                operation_held=operation.held,
                reservation_amount=amount,
            )
        ):
            raise SpendingLimitExceededError()

    async def _recover_observation(
        self, record: SpendingCallRecordDTO, observation: SpendingObservationDTO
    ) -> SpendingAccountingResultDTO | None:
        """Return the original applied result when this evidence was already recorded."""
        previous = await self._evidence(record, observation.evidence_id)
        if previous is None:
            return None
        if previous[0] != observation:
            raise ConflictError("Evidence identity changed meaning.")
        if previous[1] is not None:
            return SpendingAccountingResultDTO(previous[1], recovered=True, pending=previous[2])
        resolution = await self._resolution(record, observation.evidence_id)
        if resolution is not None:
            return SpendingAccountingResultDTO(resolution.result, recovered=True)
        return SpendingAccountingResultDTO(record, recovered=True, pending=True)

    async def _retain_pending(
        self,
        record: SpendingCallRecordDTO,
        observation: SpendingObservationDTO,
        expected_revision: int,
    ) -> SpendingAccountingResultDTO:
        """Preserve unresolved evidence without prematurely applying a charge or releasing a hold."""
        recovered = await self._recover_observation(record, observation)
        if recovered is not None:
            return recovered
        self._require_revision(record, expected_revision)
        await self._spending_ledger_writer.record_observation(
            record=record, observation=observation, applied_result=None
        )
        updated = replace(
            record, revision=SpendingAccountingService._next_revision(record.revision)
        )
        await self._spending_ledger_writer.save_call(updated, expected_revision=record.revision)
        return SpendingAccountingResultDTO(updated, pending=True)

    @staticmethod
    def _cost(
        basis: CapturedSpendingBasisDTO | None, usage: tuple[SpendingUsageDTO, ...] | None
    ) -> UsdAmount | None:
        """Calculate a charge only from the usage categories and rates accepted for this call."""
        if basis is None or usage is None:
            return None
        rates = {(rate.category, rate.unit): rate.usd_per_unit for rate in basis.rates}
        if {(item.category, item.unit) for item in usage} != rates.keys():
            return None
        exact = sum(
            (
                Fraction(rates[(item.category, item.unit)]) * Fraction(item.quantity)
                for item in usage
            ),
            Fraction(),
        )
        # Integer arithmetic retains rates below the accounting quantum and is
        # independent of the ambient Decimal context until the final round up.
        scaled = exact * 10**12
        units = -(-scaled.numerator // scaled.denominator)
        return UsdAmount(Decimal((0, tuple(int(digit) for digit in str(units)), -12)))

    @staticmethod
    def _apply_observation(
        record: SpendingCallRecordDTO, observation: SpendingObservationDTO
    ) -> SpendingCallRecordDTO:
        """Apply the supported evidence transition and retain its accounting result together."""
        zero = UsdAmount(Decimal("0"))
        if observation.kind in ("not_sent", "not_billed"):
            return replace(
                record,
                state=SpendingCallState.RELEASED,
                hold_amount=zero,
                settled_amount=zero,
                revision=SpendingAccountingService._next_revision(record.revision),
            )
        amount = (
            UsdAmount.round_up(observation.charge)
            if observation.charge is not None
            else SpendingAccountingService._cost(record.basis, observation.usage)
        )
        if amount is not None:
            return replace(
                record,
                state=SpendingCallState.SETTLED,
                hold_amount=zero,
                settled_amount=amount,
                revision=SpendingAccountingService._next_revision(record.revision),
            )
        # Missing or unsupported usage supplies no evidence to erase a prior
        # charge or release any quantified or unquantified hold.
        if record.state in (SpendingCallState.SETTLED, SpendingCallState.RELEASED):
            return replace(
                record, revision=SpendingAccountingService._next_revision(record.revision)
            )
        return replace(
            record,
            state=SpendingCallState.UNRESOLVED,
            hold_amount=None if observation.kind == "usage" else record.hold_amount,
            revision=SpendingAccountingService._next_revision(record.revision),
        )
