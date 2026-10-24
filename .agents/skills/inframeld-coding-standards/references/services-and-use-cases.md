# Write a service around a complete use case

Alice grants Bob use-only `create-access-groups` permission on Support. Alice may lose the response and retry, or her permission may change before the retry. The operation must preserve both the business change and its safeguards.

This reference teaches the implementation shape. [Application Contracts](../../inframeld-application-contracts/references/transactions-jobs-and-idempotency.md) and the [canonical service-writing guide](../../../../docs/development/application-structure.md#service-writing-guide) own transaction, replay and execution rules. Access owns authorization. Read those sources for an affected workflow rather than treating this example as a new specification.

## Contents

- [Worked example: add a complete database write](#worked-example-add-a-complete-database-write)
- [Walk through the decisions](#walk-through-the-decisions)
- [Worked example: handle a retry or failed transition](#worked-example-handle-a-retry-or-failed-transition)
- [Worked example: choose a different service shape](#worked-example-choose-a-different-service-shape)
- [Sources, status and review](#sources-status-and-review)

## Worked example: add a complete database write

**Situation.** You need an application operation that another entry point can invoke without rebuilding HTTP's authorization or database plumbing. The operation implemented by `ProjectGrantChangeService` is the reference.

**Decision and placement.** Put the public `ProjectGrantChanger` protocol and `AssignProjectUseOnlyGrantCommand` in Access application roles. Put the instantiated implementation in `application/services/project_grant_change_service.py`. Inject operational and I/O capabilities directly. Domain rules stay on the membership aggregate and policies. A repository loads and saves that aggregate, while bootstrap constructs adapters.

A transaction saves related database changes together or rolls them all back. Idempotency means repeating the same operation identity and meaning can recover its outcome without applying the change again. Neither mechanism grants permission.

**Code.** The following is the complete inspected service module, including imports, constructor, replay branch and result helper. It deliberately retains the checks surrounding load, business action and save:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/application/services/project_grant_change_service.py](../../../../apps/backend/src/inframeld_backend/access/application/services/project_grant_change_service.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from typing import override

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_use_only_grant_authorization_request_dto import (
    ProjectUseOnlyGrantAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.project_grant_authorizer import (
    ProjectGrantAuthorizer,
)
from inframeld_backend.access.application.protocols.project_grant_changer import ProjectGrantChanger
from inframeld_backend.access.application.protocols.project_membership_repository import (
    ProjectMembershipRepository,
)
from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class ProjectGrantChangeService(ProjectGrantChanger):
    def __init__(
        self,
        transactions: TransactionManager,
        authorizer: ProjectGrantAuthorizer,
        idempotency: OperationIdempotency,
        memberships: ProjectMembershipRepository,
        fingerprints: ProjectGrantChangeFingerprintService,
    ) -> None:
        self._transactions = transactions
        self._authorizer = authorizer
        self._idempotency = idempotency
        self._memberships = memberships
        self._fingerprints = fingerprints

    @override
    async def assign_use_only(
        self,
        *,
        access: AccessContextDTO,
        command: AssignProjectUseOnlyGrantCommand,
        context: OperationAdmissionContextDTO,
    ) -> CompletedSynchronousOperationDTO:
        fingerprint = self._fingerprints.for_assign_use_only(command)

        async with self._transactions.begin():
            authorization = await self._authorizer.require_authorization(
                access=access,
                request=ProjectUseOnlyGrantAuthorizationRequestDTO(
                    project_id=command.project_id,
                    recipient_principal_id=command.recipient_principal_id,
                    action_id=command.action_id,
                ),
            )

            if authorization.project_id != command.project_id:
                raise RuntimeError("Authorization returned a different project than requested.")

            operation = await self._idempotency.find_or_reserve(
                context=context,
                access=access,
                authorization=authorization,
                fingerprint=fingerprint,
                expected_replay_kind=OperationReplayKind.SAFE_RESULT,
            )

            if not isinstance(operation, NewOperationReservationDTO):
                return self._require_completed_result(operation)

            # A replay keeps its original revision. Only new work checks current state.
            if authorization.project_access_revision != command.expected_access_revision:
                raise StaleRevisionError()

            membership = await self._memberships.get(
                organization_id=authorization.organization_id,
                project_id=authorization.project_id,
                principal_id=command.recipient_principal_id,
            )
            if (
                membership.organization_id != authorization.organization_id
                or membership.project_id != authorization.project_id
                or membership.principal_id != command.recipient_principal_id
            ):
                raise RuntimeError(
                    "The loaded membership does not match the authorized assignment."
                )

            try:
                membership.assign_use_only_grant(
                    action_id=command.action_id,
                    assigned_by_principal_id=access.actor_principal_id,
                )
            except ProjectGrantAlreadyExistsError as error:
                raise ConflictError("This project action grant already exists.") from error

            await self._memberships.save(
                membership,
                expected_project_access_revision=authorization.project_access_revision,
                operation_id=operation.operation_id,
            )
            completed = await self._idempotency.record_completed_result(
                operation, replay_kind=OperationReplayKind.SAFE_RESULT
            )
            return self._require_completed_result(completed)

    @staticmethod
    def _require_completed_result(
        operation: CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO,
    ) -> CompletedSynchronousOperationDTO:
        if (
            not isinstance(operation, CompletedSynchronousOperationDTO)
            or operation.replay_kind is not OperationReplayKind.SAFE_RESULT
        ):
            raise ConflictError("The grant operation has no completed replay outcome.")
        return operation
```

## Walk through the decisions

1. **Make collaborators visible.** The constructor names transactions, the specific authorizer, idempotency, memberships and the configured fingerprint helper. It does not create a PostgreSQL repository or fetch one from a transaction object. [The composition example](component-roles-and-imports.md#worked-example-add-the-grant-operation) shows one clean session supplied to every transaction-bound adapter.
2. **Separate the inputs.** `access` identifies the authenticated caller and evidence. `command` carries the requested change. `context` carries the stable retry key, method and canonical route. The Command does not establish caller identity or permission.
3. **Compute meaning before database work.** The operation's fingerprint helper retains the canonical input and purpose. Fingerprint equality alone does not authorize replay.
4. **Open the transaction and authorize now.** `require_authorization` reads current facts under the established coordination rules. The service checks the returned project against the requested project before looking up even a completed operation. It then uses checked organization/project scope downstream.
5. **Admit or replay.** `find_or_reserve` receives context, access, current authorization, typed fingerprint and expected replay kind. A supported completed outcome returns before membership loading. New work alone checks the expected revision.
6. **Load the aggregate and verify the target.** `get` uses checked scope and the requested recipient. The service checks organization, project and principal on the returned object. A broken adapter must not redirect the mutation.
7. **Invoke the business action.** `assign_use_only_grant` owns duplicate rejection and changes the private collection. The service translates only that recognized rejection to a stable application conflict, with `from error` preserving its cause. Loading and saving stay outside this narrow catch.
8. **Save and complete together.** `save` receives the checked project-wide revision and original operation ID. The repository saves supported additions, revision and required audit without committing. Completion records share that transaction.
9. **Wait for transaction exit.** A `return` inside `async with` still waits for its exit. Commit must succeed before the caller receives the result. HTTP serialization follows successful service completion.

The load → business action → save loop is the domain-change portion of steps 6–8. Copying only those three calls would lose the operation's current authorization, scope, replay, revision, audit and completion contract.

## Worked example: handle a retry or failed transition

**Situation.** Alice loses a successful response, retries with revision `7`, and later loses delegation authority.

**Decision.** Keep replay explicit. With current authorization and matching operation identity/meaning, the saved result returns without loading or saving membership, even though the original revision is no longer current. A later attempt with revoked authority fails before idempotency lookup. A saved result is not permission.

The complete method above shows the actual branches. [The service tests](testing-and-documentation.md#worked-example-test-service-ordering-and-replay) show code proving their effects.

For new work, a stale revision stops before membership load. Wrong returned scope is an internal contract failure. A duplicate domain assignment maps to `ConflictError("This project action grant already exists.")`. Do not copy arbitrary domain exception text into that application message. Required persistence, audit and completion failures propagate, and the transaction owner rolls back. Cancellation is not a successful result.

An uncertain commit communication or lost response does not authorize new work with a fresh key. Follow the existing retry/recovery contract. The transaction manager neither retries automatically nor joins an already active transaction or creates a savepoint. Repository failure invalidates its tracked state. Discard the repository and loaded aggregates rather than attempting to continue the operation.

## Worked example: choose a different service shape

**Situation.** You add authentication instead of a grant change. A provider controls response time, and a database rollback cannot undo a remote effect.

**Decision and inspected example.** `HumanSessionAuthenticationService` injects a verifier, identity reader and recovery-block reader. Its [complete authenticate method](../../../../apps/backend/src/inframeld_backend/access/application/services/human_session_authentication_service.py) verifies the provider first, then performs local reads and decisions under explicit deadlines. It does not wrap provider verification in the grant transaction. The [independent reader example](protocols-and-persistence.md#worked-example-read-a-typed-projection) includes complete source showing the shorter session boundary.

**Other variations.** These are design variations, not claims that a new endpoint exists. Creating an aggregate constructs valid new state after authorization and applicable admission rather than loading a nonexistent object. Reads use scoped readers and typed projections. Audit and reservation writers do not need artificial aggregates. Durable jobs and remote effects retain their admission/execution/recovery contracts. Lower-level admission helpers keep caller-owned transactions unless deliberately migrated.

Do not require every service to inject all five grant collaborators. Reuse existing authorization families and operational capabilities when the workflow needs them. Do not add a generic executor, repository framework or command bus to hide the differences.

## Sources, status and review

This is an inspected example of the implemented human use-only assignment workflow, not qualification of every future command. Membership creation/removal and other grant changes remain separate work. Existing test reports remain recorded evidence unless personally rerun.

Review a proposed service by following typed input, current authority, checked target, replay branch, domain behavior, persistence and result. Check what fails before each side effect. Qualify actual behavior through domain, service and appropriate persistence tests. Do not add architecture or naming-enforcement tests.

- [Service-writing guide](../../../../docs/development/application-structure.md#service-writing-guide), [complete grant chain](../../../../docs/development/application-structure.md#grant-command-flow) and [stable domain-error mapping](../../../../docs/development/error-handling.md#stable-domain-error-mapping).
- [ADR-0065: service-owned transactions](../../../../docs/adr/ADR-0065-application-services-own-write-transactions.md), [ADR-0066: typed operation inputs](../../../../docs/adr/ADR-0066-use-typed-operation-contexts-and-command-classification.md), [ADR-0067: authorization capabilities](../../../../docs/adr/ADR-0067-standardize-authorization-capabilities-with-typed-requests.md) and [ADR-0068: membership aggregate/repository](../../../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md).
