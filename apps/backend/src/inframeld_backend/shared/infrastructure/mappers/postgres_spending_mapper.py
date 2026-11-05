from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import cast

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO
from inframeld_backend.shared.application.dtos.spending_evidence_resolution_dto import (
    SpendingEvidenceResolutionDTO,
)
from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.enums.spending_observation_kind import (
    SpendingObservationKind,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_evidence_row import (
    ModelCallAccountingEvidenceRow,
)
from inframeld_backend.shared.infrastructure.rows.model_call_accounting_row import (
    ModelCallAccountingRow,
)
from inframeld_backend.shared.infrastructure.rows.project_spending_policy_row import (
    ProjectSpendingPolicyRow,
)
from inframeld_backend.shared.infrastructure.rows.spending_operation_row import SpendingOperationRow


class PostgresSpendingMapper:
    """Convert nonsecret stored attribution and exact accounting values without I/O."""

    @staticmethod
    def amount(value: Decimal | None) -> UsdAmount | None:
        return None if value is None else UsdAmount(value)

    @staticmethod
    def to_policy(row: ProjectSpendingPolicyRow, observed_at: datetime) -> ProjectSpendingPolicyDTO:
        return ProjectSpendingPolicyDTO(
            OrganizationId(row.organization_id),
            ProjectId(row.project_id),
            row.revision,
            PostgresSpendingMapper.amount(row.monthly_limit),
            observed_at,
        )

    @staticmethod
    def to_call(
        row: ModelCallAccountingRow, operation: SpendingOperationRow
    ) -> SpendingCallRecordDTO:
        if (row.operation_id, row.organization_id, row.project_id) != (
            operation.operation_id,
            operation.organization_id,
            operation.project_id,
        ):
            raise ValueError("Stored spending attribution has inconsistent scope.")
        installation = InstallationId(operation.installation_id)
        binding = None
        if (
            operation.human_authority is not None
            and operation.human_subject is not None
            and operation.human_version is not None
        ):
            binding = HumanOAuthCredentialBindingDTO(
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(operation.human_authority),
                    IdentitySubject(operation.human_subject),
                ),
                installation,
                HumanCredentialVersion(operation.human_version),
            )
        elif any(
            value is not None
            for value in (
                operation.human_authority,
                operation.human_subject,
                operation.human_version,
            )
        ):
            raise ValueError("Stored human authority is incomplete.")
        authority = AdmittedWorkAuthorityDTO(
            principal_id=PrincipalId(operation.principal_id),
            principal_kind=PrincipalKind(operation.principal_kind),
            installation_id=installation,
            organization_id=OrganizationId(operation.organization_id),
            project_id=ProjectId(operation.project_id),
            action_id=ActionId(operation.action_id),
            human_binding=binding,
        )
        return SpendingCallRecordDTO(
            call_id=ModelCallId(row.call_id),
            operation_id=OperationId(operation.operation_id),
            authority=authority,
            job_id=JobId(operation.job_id),
            meaning_fingerprint=RequestFingerprint(row.meaning_fingerprint),
            period=SpendingPeriod(row.period_year, row.period_month),
            operation_limit=PostgresSpendingMapper.amount(operation.operation_limit),
            basis=PostgresSpendingMapper._basis(row.basis),
            reserved_amount=PostgresSpendingMapper.amount(row.reserved_amount),
            hold_amount=PostgresSpendingMapper.amount(row.hold_amount),
            settled_amount=PostgresSpendingMapper.amount(row.settled_amount),
            state=SpendingCallState(row.state),
            revision=row.revision,
            reservation_policy_revision=row.reservation_policy_revision,
            approved_policy_revision=row.approved_policy_revision,
        )

    @staticmethod
    def basis_values(basis: CapturedSpendingBasisDTO | None) -> dict[str, object] | None:
        if basis is None:
            return None
        return {
            "basis_id": basis.basis_id,
            "source_reference": basis.source_reference,
            "source_revision": basis.source_revision,
            "captured_at": basis.captured_at.isoformat(),
            "rates": [
                {
                    "category": rate.category,
                    "unit": rate.unit,
                    "usd_per_unit": str(rate.usd_per_unit),
                }
                for rate in basis.rates
            ],
            "maximum_usage": PostgresSpendingMapper.usage_values(basis.maximum_usage),
        }

    @staticmethod
    def usage_values(usage: tuple[SpendingUsageDTO, ...] | None) -> list[dict[str, object]] | None:
        if usage is None:
            return None
        return [
            {"category": item.category, "unit": item.unit, "quantity": str(item.quantity)}
            for item in usage
        ]

    @staticmethod
    def to_observation(
        row: ModelCallAccountingEvidenceRow, record: SpendingCallRecordDTO
    ) -> tuple[SpendingObservationDTO, SpendingCallRecordDTO | None, bool]:
        PostgresSpendingMapper._evidence_scope(row, record)
        if row.kind not in (
            SpendingObservationKind.USAGE,
            SpendingObservationKind.CHARGE,
            SpendingObservationKind.NOT_SENT,
            SpendingObservationKind.NOT_BILLED,
            SpendingObservationKind.UNCERTAIN,
        ):
            raise ValueError("Stored spending evidence has an unsupported kind.")
        kind = SpendingObservationKind(row.kind)
        observation = SpendingObservationDTO(
            evidence_id=row.evidence_id,
            call_id=record.call_id,
            kind=kind,
            observed_at=row.observed_at,
            source_reference=row.source_reference,
            usage=PostgresSpendingMapper._usage(row.usage),
            charge=row.charge,
        )
        applied = PostgresSpendingMapper._receipt(
            record,
            row.applied_state,
            row.applied_hold_amount,
            row.applied_settled_amount,
            row.applied_revision,
            row.applied_approved_policy_revision,
        )
        return observation, applied, row.was_pending and row.resolved_by_evidence_id is None

    @staticmethod
    def to_resolution(
        row: ModelCallAccountingEvidenceRow, record: SpendingCallRecordDTO
    ) -> SpendingEvidenceResolutionDTO | None:
        PostgresSpendingMapper._evidence_scope(row, record)
        receipt = PostgresSpendingMapper._receipt(
            record,
            row.resolution_state,
            row.resolution_hold_amount,
            row.resolution_settled_amount,
            row.resolution_revision,
            row.resolution_approved_policy_revision,
        )
        if row.resolved_by_evidence_id is None:
            if receipt is not None:
                raise ValueError("Stored resolution has no selected proof.")
            return None
        if not row.was_pending or receipt is None:
            raise ValueError("Stored resolution has no original pending outcome.")
        return SpendingEvidenceResolutionDTO(row.evidence_id, row.resolved_by_evidence_id, receipt)

    @staticmethod
    def _receipt(
        record: SpendingCallRecordDTO,
        state: str | None,
        hold: Decimal | None,
        settled: Decimal | None,
        revision: int | None,
        approval_revision: int | None,
    ) -> SpendingCallRecordDTO | None:
        """Reconstruct the accounting result recorded for this call without inventing missing fields."""
        if state is None:
            if any(value is not None for value in (hold, settled, revision, approval_revision)):
                raise ValueError("Stored financial receipt is incomplete.")
            return None
        if revision is None:
            raise ValueError("Stored financial receipt has no revision.")
        return replace(
            record,
            state=SpendingCallState(state),
            hold_amount=PostgresSpendingMapper.amount(hold),
            settled_amount=PostgresSpendingMapper.amount(settled),
            revision=revision,
            approved_policy_revision=approval_revision,
        )

    @staticmethod
    def _evidence_scope(row: ModelCallAccountingEvidenceRow, record: SpendingCallRecordDTO) -> None:
        """Reject accounting evidence stored against another model call or tenant scope."""
        if (row.call_id, row.organization_id, row.project_id) != (
            record.call_id.value,
            record.authority.organization_id.value,
            record.authority.project_id.value,
        ):
            raise ValueError("Stored evidence changed its original scope.")

    @staticmethod
    def _basis(value: dict[str, object] | None) -> CapturedSpendingBasisDTO | None:
        """Decode the rate basis retained when the model call was reserved."""
        if value is None:
            return None
        rates: list[SpendingRateDTO] = []
        for item in PostgresSpendingMapper._items(value.get("rates")):
            rate = PostgresSpendingMapper._object(item)
            rates.append(
                SpendingRateDTO(
                    PostgresSpendingMapper._text(rate.get("category")),
                    PostgresSpendingMapper._text(rate.get("unit")),
                    Decimal(PostgresSpendingMapper._text(rate.get("usd_per_unit"))),
                )
            )
        return CapturedSpendingBasisDTO(
            basis_id=PostgresSpendingMapper._text(value.get("basis_id")),
            source_reference=PostgresSpendingMapper._text(value.get("source_reference")),
            source_revision=PostgresSpendingMapper._text(value.get("source_revision")),
            captured_at=datetime.fromisoformat(
                PostgresSpendingMapper._text(value.get("captured_at"))
            ),
            rates=tuple(rates),
            maximum_usage=PostgresSpendingMapper._usage(value.get("maximum_usage")),
        )

    @staticmethod
    def _usage(value: object) -> tuple[SpendingUsageDTO, ...] | None:
        """Decode retained usage quantities without accepting an untyped accounting payload."""
        if value is None:
            return None
        result: list[SpendingUsageDTO] = []
        for item in PostgresSpendingMapper._items(value):
            usage = PostgresSpendingMapper._object(item)
            result.append(
                SpendingUsageDTO(
                    PostgresSpendingMapper._text(usage.get("category")),
                    PostgresSpendingMapper._text(usage.get("unit")),
                    Decimal(PostgresSpendingMapper._text(usage.get("quantity"))),
                )
            )
        return tuple(result)

    @staticmethod
    def _text(value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("Stored spending text is malformed.")
        return value

    @staticmethod
    def _items(value: object) -> list[object]:
        if not isinstance(value, list):
            raise ValueError("Stored spending sequence is malformed.")
        # JSON persistence is narrowed here before typed application conversion.
        return cast(list[object], value)

    @staticmethod
    def _object(value: object) -> dict[str, object]:
        if not isinstance(value, dict):
            raise ValueError("Stored spending object is malformed.")
        record = cast(dict[object, object], value)
        if any(not isinstance(key, str) for key in record):
            raise ValueError("Stored spending object keys are malformed.")
        return cast(dict[str, object], record)
