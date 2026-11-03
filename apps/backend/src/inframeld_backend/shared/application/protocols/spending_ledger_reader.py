from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
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
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod


class SpendingLedgerReader(Protocol):
    """Observe exact scoped ledger records in the owning transaction.

    Acquire authorization, workload job ownership, then accounting locks. Never
    acquire an earlier lock after accounting. Unlocked call reads establish
    binding only. Pending completeness changes require a locked call reread too.
    """

    @abstractmethod
    async def find_call(
        self, *, organization_id: OrganizationId, project_id: ProjectId, call_id: ModelCallId
    ) -> SpendingCallRecordDTO | None: ...

    @abstractmethod
    async def lock_project_policy(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectSpendingPolicyDTO: ...

    @abstractmethod
    async def project_totals(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        period: SpendingPeriod,
        exclude_call_id: ModelCallId | None = None,
    ) -> SpendingTotalsDTO: ...

    @abstractmethod
    async def operation_totals(
        self, *, record: SpendingCallRecordDTO, exclude_call_id: ModelCallId | None = None
    ) -> SpendingTotalsDTO: ...

    @abstractmethod
    async def observation(
        self, *, record: SpendingCallRecordDTO, evidence_id: UUID
    ) -> tuple[SpendingObservationDTO, SpendingCallRecordDTO | None, bool] | None:
        """Read evidence, its original financial receipt and unresolved-marker status.

        The final bool reports an unresolved pending marker independently of
        the financial receipt. Applying proof does not resolve its own marker.
        A later correction never replaces an earlier receipt. Observations and
        receipts remain bound to the same original call and scope.
        """
        ...

    @abstractmethod
    async def resolution(
        self, *, record: SpendingCallRecordDTO, pending_evidence_id: UUID
    ) -> SpendingEvidenceResolutionDTO | None:
        """Read one item's original resolution without interpreting financial replay."""
        ...

    @abstractmethod
    async def project_projection(
        self, *, organization_id: OrganizationId, project_id: ProjectId, period: SpendingPeriod
    ) -> SpendingProjectionDTO:
        """Return policy/totals/unknown obligations from one SQL statement snapshot.

        Inspection creates no coordination row and performs no sequential policy
        and balance reads. Unavailable accounting is an error, not an empty ledger.
        """
        ...

    @abstractmethod
    async def policy_result(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_id: PrincipalId,
        completion: CompletedSynchronousOperationDTO,
    ) -> ProjectSpendingPolicyResultDTO: ...
