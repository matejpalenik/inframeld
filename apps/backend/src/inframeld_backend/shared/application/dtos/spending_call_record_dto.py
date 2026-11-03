from dataclasses import dataclass

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


@dataclass(frozen=True, slots=True)
class SpendingCallRecordDTO:
    """Observe original attribution and accounting state without authorizing dispatch."""

    call_id: ModelCallId
    operation_id: OperationId
    authority: AdmittedWorkAuthorityDTO
    job_id: JobId
    meaning_fingerprint: RequestFingerprint
    period: SpendingPeriod
    operation_limit: UsdAmount | None
    basis: CapturedSpendingBasisDTO | None
    reserved_amount: UsdAmount | None
    hold_amount: UsdAmount | None
    settled_amount: UsdAmount | None
    state: SpendingCallState
    revision: int
    reservation_policy_revision: int
    approved_policy_revision: int | None = None
