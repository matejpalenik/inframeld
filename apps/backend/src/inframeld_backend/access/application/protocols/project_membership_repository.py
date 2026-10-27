from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.domain.entities.project_membership import ProjectMembership
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class ProjectMembershipRepository(Protocol):
    """Load and save membership grants in an already authorized transaction.

    Use the same request-local session as authorization and idempotency. The
    caller owns the transaction and existing organization/project locks. Keep
    original value snapshots outside the entity, independently of ID equality.
    """

    @abstractmethod
    async def get(
        self, *, organization_id: OrganizationId, project_id: ProjectId, principal_id: PrincipalId
    ) -> ProjectMembership:
        """Load an existing membership and its complete direct project grants.

        Repeated loads in this transaction return the same instance. Never
        provision a missing membership or infer permission from its existence.

        Args:
            organization_id: Organization established by current authorization.
            project_id: Project matched against the requested target.
            principal_id: Recipient whose grants will change, not the caller.

        Returns:
            The existing membership, including an empty collection if it has no
            direct project grants.

        Raises:
            ResourceNotFoundError: The membership is absent in the requested scope.
            RuntimeError: There is no active caller transaction, or this repository
                has already failed or belongs to an ended transaction.
        """
        ...

    @abstractmethod
    async def save(
        self,
        membership: ProjectMembership,
        *,
        expected_project_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        """Save new use-only grants and their required audit without committing.

        Save only the instance loaded here in this transaction. An unchanged
        save does no writes. For additions, advance the active project's revision
        once, insert without overwriting assignments, and append typed audit
        events correlated with the original operation ID. Preserve existing
        grants and their database-generated attribution timestamps.

        Update snapshots after all writes succeed. Following a failed save or
        transaction end, discard the repository and its aggregates. Persistence
        errors and cancellation propagate for the owner to roll back.

        Args:
            membership: The exact loaded instance after its domain transition.
            expected_project_access_revision: Current checked project revision,
                shared by every member. This is not a membership version.
            operation_id: Original reservation identity for audit correlation.

        Raises:
            ConflictError: The project revision or state changed, or an assignment
                already exists in storage.
            RuntimeError: The instance was not loaded here, its original state
                was modified or removed, or additions are not attributed use-only
                assignments. Also reject missing or ended transactions and reuse
                after a failed save.
        """
        ...
