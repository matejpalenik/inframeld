from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.spending_accounting_result_dto import (
    SpendingAccountingResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_context_dto import (
    SpendingCallContextDTO,
)
from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


class SpendingAccountant(Protocol):
    """Coordinate internal accounting without granting model dispatch authority.

    Workload operations require the immutable original product-job binding and
    actual current authority/ownership checks. Ports share the caller's transaction.
    Trusted callers establish provider evidence and pricing coverage separately.
    """

    @abstractmethod
    async def reserve(
        self,
        *,
        call: SpendingCallContextDTO,
        basis: CapturedSpendingBasisDTO | None,
        operation_limit: UsdAmount | None,
    ) -> SpendingAccountingResultDTO: ...

    @abstractmethod
    async def approve_accounting(
        self, *, call: SpendingCallContextDTO, expected_call_revision: int
    ) -> SpendingAccountingResultDTO: ...

    @abstractmethod
    async def record_observation(
        self,
        *,
        call: SpendingCallContextDTO,
        observation: SpendingObservationDTO,
        expected_call_revision: int,
    ) -> SpendingAccountingResultDTO:
        """Retain recognized stale-fence evidence normally, without applying it.

        Only an existing, exactly bound call after current authorization permits
        pending retention. Invalid binding, denial, database errors and cancellation
        propagate for rollback. A pending result commits no financial transition.
        """
        ...

    @abstractmethod
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
        """Resolve one explicitly reviewed pending item under current human authority.

        Keep immutable evidence and financial receipts. Save the selected proof,
        audit and this resolution's own outcome together. A matching resolution
        replay returns that outcome before new-work revision checks. It cannot
        reapply a debit or resolve a different pending item.
        """
        ...
