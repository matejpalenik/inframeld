from abc import abstractmethod
from typing import Protocol
from uuid import UUID

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
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
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


class SpendingLedgerWriter(Protocol):
    """Persist checked ledger transitions and required audit without committing."""

    @abstractmethod
    async def ensure_project_account(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> None:
        """Insert only absent no-limit/revision-zero coordination, on conflict do nothing.

        The caller follows with a scoped locked reread. Never update an existing
        policy, modify Project creation or retry the transaction automatically.
        """
        ...

    @abstractmethod
    async def ensure_operation(
        self, *, call: SpendingCallContextDTO, operation_limit: UsdAmount | None
    ) -> None:
        """Retain the original operation/job/authority/limit binding without a replay TTL."""
        ...

    @abstractmethod
    async def insert_call(self, record: SpendingCallRecordDTO) -> None: ...

    @abstractmethod
    async def save_call(self, record: SpendingCallRecordDTO, *, expected_revision: int) -> None: ...

    @abstractmethod
    async def record_observation(
        self,
        *,
        record: SpendingCallRecordDTO,
        observation: SpendingObservationDTO,
        applied_result: SpendingCallRecordDTO | None,
    ) -> None:
        """Append evidence and its financial receipt, or pending None, without call mutation.

        Keep the receipt on this evidence record. Its state, amounts, revision
        and approval revision combine with immutable original call attribution
        and basis on reads. No second call, basis or mutable policy copy is needed.
        """
        ...

    @abstractmethod
    async def mark_observation_applied(
        self, *, record: SpendingCallRecordDTO, evidence_id: UUID, result: SpendingCallRecordDTO
    ) -> None:
        """Retain the first financial receipt without resolving any pending marker."""
        ...

    @abstractmethod
    async def record_resolution(
        self, *, record: SpendingCallRecordDTO, resolution: SpendingEvidenceResolutionDTO
    ) -> None:
        """Set one pending item's one-time resolution without changing its payload or applied receipt."""
        ...

    @abstractmethod
    async def save_correction_audit(
        self,
        *,
        actor_id: PrincipalId,
        resolution: SpendingEvidenceResolutionDTO,
        previous_revision: int,
    ) -> None: ...

    @abstractmethod
    async def change_policy(
        self,
        *,
        policy: ProjectSpendingPolicyDTO,
        expected_revision: int,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None: ...

    @abstractmethod
    async def save_policy_result(
        self,
        *,
        policy: ProjectSpendingPolicyDTO,
        actor_id: PrincipalId,
        operation_id: OperationId,
        changed: bool,
    ) -> None: ...
