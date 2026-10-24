# Change an aggregate through its specific repository

Bob can hold several direct action grants on Support. Adding one must preserve the others and reject an existing assignment. Loading one membership and its complete direct collection gives this rule a focused owner without loading every member of the Project.

An aggregate is the domain object responsible for a group of state that must stay consistent. A repository is its application-owned loading and persistence capability. Neither term means a generic CRUD framework, a database row or proof of permission.

## Contents

- [Worked example: give the transition a domain owner](#worked-example-give-the-transition-a-domain-owner)
- [Worked example: define the specific repository](#worked-example-define-the-specific-repository)
- [Worked example: save supported changes without committing](#worked-example-save-supported-changes-without-committing)
- [Status and evidence](#status-and-evidence)

## Worked example: give the transition a domain owner

**Situation.** You need to add an assignment while preventing callers from overwriting or downgrading Bob's existing grant.

**Decision and placement.** Access's `ProjectMembership` belongs in domain entities. It owns the private grant collection and exposes immutable children. The complete implementation shows construction checks as well as the business method:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/domain/entities/project_membership.py](../../../../apps/backend/src/inframeld_backend/access/domain/entities/project_membership.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from typing import override

from inframeld_backend.access.domain.entities.project_action_grant import ProjectActionGrant
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectMembership:
    """Own one member's complete collection of direct project action grants.

    Membership alone grants no action permission. Authorization separately checks
    current eligibility, delegation authority and project availability. This
    aggregate protects assignment transitions without persistence bookkeeping.
    """

    def __init__(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        principal_id: PrincipalId,
        principal_kind: PrincipalKind,
        grants: tuple[ProjectActionGrant, ...],
    ) -> None:
        grants_by_action: dict[ActionId, ProjectActionGrant] = {}
        for grant in grants:
            if grant.project_id != project_id or grant.recipient_principal_id != principal_id:
                raise ValueError("A grant belongs to another project membership.")
            if grant.action_id in grants_by_action:
                raise ValueError("A membership contains duplicate action grants.")
            if (
                principal_kind is PrincipalKind.APPLICATION
                and grant.level is ProjectGrantLevel.USE_AND_GRANT
            ):
                raise ValueError("Applications cannot hold delegation rights.")
            grants_by_action[grant.action_id] = grant

        self._organization_id = organization_id
        self._project_id = project_id
        self._principal_id = principal_id
        self._principal_kind = principal_kind
        self._grants = grants_by_action

    @property
    def identity(self) -> tuple[ProjectId, PrincipalId]:
        return self._project_id, self._principal_id

    @property
    def organization_id(self) -> OrganizationId:
        return self._organization_id

    @property
    def project_id(self) -> ProjectId:
        return self._project_id

    @property
    def principal_id(self) -> PrincipalId:
        return self._principal_id

    @property
    def principal_kind(self) -> PrincipalKind:
        return self._principal_kind

    @property
    def grants(self) -> tuple[ProjectActionGrant, ...]:
        """Expose immutable children without allowing collection mutation."""
        return tuple(self._grants.values())

    def assign_use_only_grant(
        self, *, action_id: ActionId, assigned_by_principal_id: PrincipalId
    ) -> None:
        """Assign a missing action without replacing or downgrading another grant.

        Raises:
            ProjectGrantAlreadyExistsError: The action is already assigned at
                either permission level. Leave the aggregate unchanged.
        """
        if action_id in self._grants:
            raise ProjectGrantAlreadyExistsError("This project action grant already exists.")
        grant = ProjectActionGrant.create_use_only(
            project_id=self._project_id,
            recipient_principal_id=self._principal_id,
            action_id=action_id,
            assigned_by_principal_id=assigned_by_principal_id,
        )
        self._grants[action_id] = grant

    @override
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProjectMembership):
            return NotImplemented
        return self.identity == other.identity

    @override
    def __hash__(self) -> int:
        return hash(self.identity)
```

**Walkthrough.** The constructor reconstitutes the complete collection and rejects duplicate actions, wrong-scope children and application delegation rights. `grants` returns an immutable tuple. `assign_use_only_grant` expresses the requested business action, rejects an already assigned action at either level, and creates the new attributed child only after that check.

The aggregate identity is project plus principal. Organization and kind are read-only metadata. `ProjectActionGrant` children are immutable and have natural identity project plus recipient plus action. Level and attribution are state. Equality by entity identity does not establish that those state values are unchanged.

**Failure and alternatives.** A duplicate leaves the aggregate unchanged. It does not query current permission or decide whether Alice may delegate to Bob. Policies decide from explicit facts, and the authorizer obtains current facts. The service checks returned scope and maps a known rejection. Avoid service code that edits `_grants`, chooses rules by inspecting a public mutable collection, or asks a field writer to bypass the transition.

Value objects protect their own invariants, and pure policies may consume several objects or explicit facts. Not every DTO or supporting audit record needs an aggregate.

## Worked example: define the specific repository

**Situation.** The service must load Bob's existing membership, execute its action and save the supported change without knowing SQLAlchemy.

**Decision and placement.** Declare `ProjectMembershipRepository` in Access application protocols. Its public contract names trusted scope, transaction ownership, required audit and supported changes. This is the complete existing module:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/application/protocols/project_membership_repository.py](../../../../apps/backend/src/inframeld_backend/access/application/protocols/project_membership_repository.py). This is existing code for explanation, not replacement or insertion instructions.

```python
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
```

**Walkthrough.** The service passes checked organization/project IDs and the requested recipient to `get`. The adapter loads an existing membership and all its direct grants. Missing membership raises the existing not-found failure and never provisions a membership. Repeated loads in the active transaction return the same instance. The service verifies the returned target before invoking domain behavior.

The full [service example](services-and-use-cases.md#worked-example-add-a-complete-database-write) shows `get`, `assign_use_only_grant` and `save` inside their actual safeguards. The expected revision supplied to save belongs to the whole Project, not one membership. `operation_id` is the original reservation identity used for required audit correlation.

**Failure and alternatives.** Loading a membership grants no action permission. A repository does not replace authorization. A read projection needs no save method. Creation needs a separately designed persistence contract rather than changing this `get` into an implicit create. Keep supporting audit and reservation writers as focused capabilities.

## Worked example: save supported changes without committing

**Situation.** PostgreSQL must preserve existing assignments and timestamps, add the supported grants, advance the Project revision once and append required audit. A failure must not leave the adapter's in-memory state trustworthy.

**Decision and placement.** Use `PostgresProjectMembershipRepository` under Access infrastructure repositories. Its constructor receives the caller's `AsyncSession` and session-bound audit writer. It tracks exact loaded instances and immutable value snapshots outside the entity.

The following is the complete inspected `save` method in its class context. This is a selected adapter excerpt, not a standalone implementation. Its constructor, snapshot types and helper methods remain in the linked source. `_require_transaction` checks active transaction ownership, `_snapshot` and `_additions` compute value changes, and the two async helpers perform the typed revision/grant/audit writes.

**Inspected teaching excerpt:** the complete save method in its class context from [apps/backend/src/inframeld_backend/access/infrastructure/repositories/postgres_project_membership_repository.py](../../../../apps/backend/src/inframeld_backend/access/infrastructure/repositories/postgres_project_membership_repository.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from typing import override

from inframeld_backend.access.application.protocols.project_membership_repository import (
    ProjectMembershipRepository,
)
from inframeld_backend.access.domain.entities.project_membership import (
    ProjectMembership,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


class PostgresProjectMembershipRepository(ProjectMembershipRepository):
    @override
    async def save(
        self,
        membership: ProjectMembership,
        *,
        expected_project_access_revision: int,
        operation_id: OperationId,
    ) -> None:
        try:
            self._require_transaction()
            key = (
                membership.organization_id,
                membership.project_id,
                membership.principal_id,
            )
            tracked = self._tracked.get(key)
            if tracked is None or tracked.membership is not membership:
                raise RuntimeError("Save only the membership instance loaded by this repository.")
            current = _snapshot(membership)
            additions = _additions(tracked.snapshot, current)
            if not additions:
                return
            await self._advance_revision(current, expected_project_access_revision)
            for grant in additions:
                await self._insert_grant(current, grant, operation_id)
            tracked.snapshot = current
        except BaseException:
            # Cancellation also invalidates snapshots. The transaction owner rolls back.
            self._failed = True
            raise
```

**Walkthrough.** The adapter accepts only the exact object loaded by this repository. Its snapshots compare level and attribution independently of the children's identity equality. `_additions` rejects changed metadata, removal, modification and additions lacking use-only level or attribution. No additions means no writes. Supported additions conditionally advance the active project's checked revision once, insert without overwriting assignments, and append typed audit with the original operation ID. Existing database timestamps and values remain unchanged. The snapshot advances only after all writes and audit succeed.

**Failure.** A failed or cancelled save marks the repository unusable and propagates the error for the transaction owner to roll back. The broad `BaseException` catch here invalidates local state and immediately re-raises. It does not turn unexpected failures into a domain rejection, suppress cancellation or authorize a retry. A transaction end also invalidates repository/aggregate reuse. Discard them after commit, rollback or failed save.

The adapter opens no transaction, acquires no explicit coordination locks, commits nothing and retries nothing. The current authorizer/service and database constraints retain their existing coordination responsibilities. Do not catch a failed save and continue toward commit.

## Status and evidence

Only the current attributed use-only addition workflow is implemented by this repository. Membership creation/removal, arbitrary updates, revocation and cross-member lifecycle operations remain deferred. The existing boolean storage representation, nullable historical attribution and timestamps are preserved. Do not invent a membership revision, generic `Repository[T]`, Unit of Work service locator or additional schema to imitate this example.

Behavior tests should cover accepted/rejected transitions, exact scoped instances, unchanged saves, value preservation, revision conflicts, required audit and rollback. Existing integration scenarios are evidence of what was recorded or inspected, not checks personally rerun by reading this reference.

- [Canonical aggregate/repository explanation](../../../../docs/development/application-structure.md#membership-aggregate-and-repository), [data-model ownership](../../../../docs/development/data-model.md#project-membership-aggregate) and [ADR-0068](../../../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md).
- [Immutable grant child](../../../../apps/backend/src/inframeld_backend/access/domain/entities/project_action_grant.py), [repository adapter and helpers](../../../../apps/backend/src/inframeld_backend/access/infrastructure/repositories/postgres_project_membership_repository.py) and [PostgreSQL behavior scenarios](../../../../apps/backend/tests/integration/access/test_project_membership_repository_postgres.py).
- [Application transaction ownership](../../inframeld-application-contracts/references/transactions-jobs-and-idempotency.md) and [behavioral testing examples](testing-and-documentation.md).
