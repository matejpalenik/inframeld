from dataclasses import dataclass

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)


@dataclass(frozen=True, slots=True)
class SpendingCallContextDTO:
    """Retain the original call, operation and mandatory admitted job attempt.

    Matching records establish only binding coherence. The owning application
    still checks current authority and actual job ownership inside its transaction.
    """

    call_id: ModelCallId
    operation_id: OperationId
    authority: AdmittedWorkAuthorityDTO
    attempt: JobAttemptContextDTO
    meaning_fingerprint: RequestFingerprint

    def __post_init__(self) -> None:
        binding = self._require_attempt(self.attempt).binding
        if not isinstance(binding, ProductJobBindingDTO):
            raise ValueError("Accounting requires a product job binding.")
        if binding.operation_id != self.operation_id or binding.authority != self.authority:
            raise ValueError("Accounting must preserve the original operation and authority.")

    @staticmethod
    def _require_attempt(value: object) -> JobAttemptContextDTO:
        if not isinstance(value, JobAttemptContextDTO):
            raise TypeError("Accounting requires an admitted product job attempt.")
        return value
