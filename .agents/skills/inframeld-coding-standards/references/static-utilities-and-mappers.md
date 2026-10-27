# Static utilities, policies and mappers

<a id="static-utilities-policies-and-mappers"></a>

Alice needs the same parsed-UUID check in several identifier classes. A named `ValueValidation` class makes the shared operation visible at every call site. It is a group of pure static methods, not an object that holds a database connection or current user.

<a id="choose-the-right-kind-of-behavior"></a>

## Choose the right kind of behavior

Default reusable pure production conversion and validation utilities to cohesive named classes with `@staticmethod` methods. Import the class directly and call it by name. Do not replace that convention with public standalone utility functions or module-qualified utility calls.

Keep each class focused on one purpose. Do not collect unrelated helpers in `Utils`, add mutable class state or create a class solely to wrap a small private function. Small private helpers, test fixtures and framework-required callables may remain functions. Standard-library and SDK module imports are not prohibited.

Services stay instantiated because they orchestrate workflows through injected collaborators. Entities own their state transitions. Value objects own their specific invariants. A static utility must not take over those responsibilities. A check that performs provider or database I/O belongs to an appropriate instantiated service or adapter.

<a id="shared-validation"></a>

## Shared validation

Shared primitive checks belong to `ValueValidation` in `shared/domain/validation/value_validation.py`. Import the class and call `ValueValidation.require_uuid(value)` or `ValueValidation.require_string(value)`. Value-specific rules stay on the owning value object.

The following is an existing complete method in its class context from `apps/backend/src/inframeld_backend/shared/domain/validation/value_validation.py`. It is a read-only teaching excerpt, not replacement or insertion instructions:

```python
from uuid import UUID

class ValueValidation:
    """Check shared runtime types before values enforce their own invariants."""

    @staticmethod
    def require_uuid(value: object) -> None:
        """Reject unparsed input, including another ID wrapper, at value construction."""
        if not isinstance(value, UUID):
            raise TypeError("An identifier requires a parsed UUID.")
```

This check rejects a raw string or another ID wrapper. It does not reject valid UUID versions or zero values, prove that a record exists, or decide access. Secret validation errors must not include secret contents.

<a id="pure-policies-and-boundary-mappers"></a>

## Pure policies and boundary mappers

Policies receive explicit inputs and have no I/O or mutable class state. Use `@staticmethod` and qualified calls such as `ActionAuthorizationPolicy.may_perform_action(policy_input)`. Policies may accept an existing entity or typed parameters. A new wrapper is not required merely for naming symmetry.

Feature HTTP mappings use static `*Mapper` classes in `mappers/*_mapper.py`. They convert validated HTTP input into Command inputs and application results into responses. Shared database conversion uses technology-prefixed static `*Mapper` classes in `infrastructure/mappers` when several adapters need the same conversion. Neither kind performs I/O or authorization.

In the existing `apps/backend/src/inframeld_backend/access/http/mappers/project_use_only_grant_mapper.py`, `ProjectUseOnlyGrantMapper.to_command` wraps parsed UUIDs as `ProjectId` and `PrincipalId`. It does not load membership, authorize the actor or decide fingerprint meaning. The application service owns those steps.

<a id="worked-example-map-an-http-request-without-doing-the-work"></a>

## Worked example: map an HTTP request without doing the work

**Situation.** A request contains a parsed project UUID and Bob's recipient UUID. The service needs application-owned identifiers and a Command, and the response needs published primitive fields.

**Decision and placement.** Add a static mapper under the owning feature's `http/mappers`. Input conversion does not need a current-user field, database session or instance state. This is the complete existing grant mapper:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/http/mappers/project_use_only_grant_mapper.py](../../../../apps/backend/src/inframeld_backend/access/http/mappers/project_use_only_grant_mapper.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from uuid import UUID

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.requests.project_use_only_grant_request import (
    ProjectUseOnlyGrantRequest,
)
from inframeld_backend.access.http.responses.project_use_only_grant_response import (
    ProjectUseOnlyGrantResponse,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.operation_admission_context_dto import (
    OperationAdmissionContextDTO,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey

class ProjectUseOnlyGrantMapper:
    """Convert the published grant contract without performing authorization or I/O."""

    @staticmethod
    def to_command(
        *, project_id: UUID, request: ProjectUseOnlyGrantRequest
    ) -> AssignProjectUseOnlyGrantCommand:
        return AssignProjectUseOnlyGrantCommand(
            project_id=ProjectId(project_id),
            recipient_principal_id=PrincipalId(request.recipient_principal_id),
            action_id=ActionId(request.action_id),
            expected_access_revision=request.expected_access_revision,
        )

    @staticmethod
    def to_operation_context(key: IdempotencyKey) -> OperationAdmissionContextDTO:
        return OperationAdmissionContextDTO(
            method="POST", requested_route="/v1/projects/{project_id}/grants", key=key
        )

    @staticmethod
    def to_response(
        *, command: AssignProjectUseOnlyGrantCommand, result: CompletedSynchronousOperationDTO
    ) -> ProjectUseOnlyGrantResponse:
        action = command.action_id.value
        if action != "create-access-groups":
            raise ValueError("Unsupported project grant action.")
        return ProjectUseOnlyGrantResponse(
            operation_id=result.operation_id.value,
            project_id=command.project_id.value,
            recipient_principal_id=command.recipient_principal_id.value,
            action_id=action,
            access_revision=command.expected_access_revision + 1,
            idempotency_expires_at=result.expires_at,
        )
```

**Walkthrough.** `to_command` wraps parsed values without treating them as proof of existence or permission. `to_operation_context` preserves the canonical route and retry key separately from the business input. `to_response` serializes the completed operation and the original Command's meaning. It runs after the service has committed. Its `+ 1` follows this grant operation's published revision contract, not a general rule for response mappers.

**Failures and alternatives.** The supported-action check can fail. It does not authorize the action or replace the request schema. Do not add membership reads, fingerprint decisions or persistence to this mapper. Preserve published names and supported values when adapting this convention.

<a id="worked-example-share-stored-value-conversion"></a>

## Worked example: share stored-value conversion

**Situation.** Credential readers need to turn a typed database result into a named application result. The conversion should not be copied between readers.

**Decision and placement.** Use a technology-prefixed static mapper under `infrastructure/mappers`. The reader does I/O, and the mapper only interprets the result it receives:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/infrastructure/mappers/postgres_human_credential_state_mapper.py](../../../../apps/backend/src/inframeld_backend/access/infrastructure/mappers/postgres_human_credential_state_mapper.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from uuid import UUID

from inframeld_backend.access.application.dtos.human_credential_state_dto import (
    HumanCredentialStateDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

class PostgresHumanCredentialStateMapper:
    """Convert stored credential state without initializing it or deciding eligibility."""

    @staticmethod
    def to_state(
        identity: VerifiedHumanIdentityDTO, row: tuple[UUID, int | None, bool, bool] | None
    ) -> HumanCredentialStateDTO:
        if row is None:
            raise DependencyUnavailableError("The installation identity is not available.")
        installation_id, version, pending, _history = row
        return HumanCredentialStateDTO(
            installation_id=InstallationId(installation_id),
            identity=identity,
            version=HumanCredentialVersion(version) if version is not None else None,
            has_pending_recovery=pending,
        )
```

**Walkthrough.** A stored UUID becomes `InstallationId`, and an available version becomes `HumanCredentialVersion`. A missing version remains explicitly absent. The mapper returns a DTO with named fields instead of leaking tuple offsets to the application.

**Failure.** A missing installation row is unavailable metadata, not evidence of no recovery block or a successful empty result. The mapper neither initializes state nor decides eligibility. [The reader example](protocols-and-persistence.md#worked-example-read-a-typed-projection) shows where query execution and recognized availability translation belong.

<a id="worked-example-decide-with-a-policy"></a>

## Worked example: decide with a policy

**Situation.** Alice may delegate an action only if the supplied facts establish the required eligibility and exact-action permission. Loading those facts and deciding from them are separate jobs.

**Decision and placement.** Put the pure decision in Access domain policies. The following complete method, in its class context, is an existing policy example:

**Inspected teaching excerpt:** the complete may_delegate_project_action method in its class context from [apps/backend/src/inframeld_backend/access/domain/policies/project_grant_delegation_policy.py](../../../../apps/backend/src/inframeld_backend/access/domain/policies/project_grant_delegation_policy.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import (
    PrincipalAccessPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)

class ProjectGrantDelegationPolicy:
    @staticmethod
    def may_delegate_project_action(
        *,
        actor_access: PrincipalAccessPolicyInput,
        actor_is_project_member: bool,
        actor_can_grant_action: bool,
    ) -> bool:
        """Check the grantor before revealing anything about the recipient."""
        return (
            actor_access.principal.kind is PrincipalKind.HUMAN
            and PrincipalAccessPolicy.may_use_product(actor_access)
            and actor_is_project_member
            and actor_can_grant_action
        )
```

**Walkthrough and failure.** The qualified class call makes the decision visible. A false decision becomes an application rejection in the authorizer, not database work inside the policy. This method alone does not establish recipient eligibility. The owning authorizer also invokes the recipient-specific policy after checking visibility and delegation. Keep [Access authorization](../../inframeld-access-models/references/authorization.md) authoritative for that order.

<a id="correct-exceptions-private-functions-and-injected-helpers"></a>

## Correct exceptions: private functions and injected helpers

**Situation.** Not every callable should become a static method. The membership repository's private `_snapshot` and `_additions` functions describe its local bookkeeping. They may remain functions rather than becoming a reusable production utility API.

The existing `ProjectGrantChangeFingerprintService` is another useful distinction. It receives `RequestFingerprintService`, which holds an injected secret key. Making it a static utility would hide that configured dependency or force it into global state. Its complete implementation is:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/application/services/project_grant_change_fingerprint_service.py](../../../../apps/backend/src/inframeld_backend/access/application/services/project_grant_change_fingerprint_service.py). This is existing code for explanation, not replacement or insertion instructions.

```python
"""Fingerprint the meaningful fields of a project grant command."""

from json import dumps

from inframeld_backend.access.application.commands.assign_project_use_only_grant_command import (
    AssignProjectUseOnlyGrantCommand,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)

_ASSIGN_USE_ONLY_PURPOSE = "access.project-grant.assign-use-only:v1"

class ProjectGrantChangeFingerprintService:
    """Define grant-command meaning before the shared keyed fingerprint is made."""

    def __init__(self, fingerprints: RequestFingerprintService) -> None:
        self._fingerprints = fingerprints

    def for_assign_use_only(self, command: AssignProjectUseOnlyGrantCommand) -> RequestFingerprint:
        """Retain the canonical request bytes used by existing reservations."""
        canonical_request = dumps(
            {
                "actionId": command.action_id.value,
                "expectedAccessRevision": command.expected_access_revision,
                "projectId": str(command.project_id.value),
                "recipientPrincipalId": str(command.recipient_principal_id.value),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return self._fingerprints.fingerprint(
            purpose=_ASSIGN_USE_ONLY_PURPOSE, canonical_request=canonical_request
        )
```

The exact purpose, canonical bytes and key stability matter to existing reservations. Reuse the operation's helper, not a new hash chosen by a mapper. Pure computation does not require static methods when the component deliberately holds injected configuration or collaborators. Fixtures and framework callables remain valid functions. See the [aggregate adapter example](aggregates-and-repositories.md) for local private helpers and the [service example](services-and-use-cases.md) for orchestration.

<a id="failures-and-review"></a>

## Failures and review

A conversion failure cannot become a permission denial or a successful empty result. Keep recognized domain-error translation in the service and leave I/O failures at their documented boundary. Pure utilities have no retry or transaction ownership.

When reviewing a helper, ask whether it is reusable production behavior, a small private detail, a framework callback or stateful orchestration. Apply the matching convention instead of requiring every function or every service to become static.

<a id="qualified-policy-calls"></a>

### Qualified policy calls

Call pure business decisions through their policy class:

| Call | Decision |
| --- | --- |
| `HumanAuthenticationPolicy.may_authenticate(...)` | Is the linked principal a currently eligible human? |
| `ProjectVisibilityPolicy.may_view_project(...)` | May this caller learn that the organization-scoped project exists? |
| `ActionAuthorizationPolicy.may_perform_action(policy_input)` | Does current eligibility include the exact requested grant? |

Policy methods use `@staticmethod`, explicit inputs, and no I/O or mutable class state. Services own orchestration and their injected collaborators.

<a id="static-utilities-and-mappers"></a>

### Static utilities and mappers

Default reusable pure production conversion and validation utilities to cohesive named classes with `@staticmethod` methods. Import the class directly and call it by name. For example, import `ValueValidation` from its defining module and call `ValueValidation.require_uuid(value)`, rather than exposing a standalone check or using a module-qualified utility call. Shared primitive checks belong to `ValueValidation` in `shared/domain/validation/value_validation.py`. Value-specific invariants stay on their owning value objects.

Keep static utility classes focused on one purpose and free of I/O or mutable class state. Do not collect unrelated functions in miscellaneous `Utils` classes. Small private helpers, test fixtures and framework-required callables may remain functions. Standard-library and SDK module imports remain valid where appropriate.

Feature HTTP mappers and shared technology-prefixed persistence mappers retain their required static roles and perform no I/O or authorization. Services remain instantiated with injected collaborators. Entities own state transitions. This utility preference does not convert stateful workflows into static methods or automatically migrate existing helpers.

Use dedicated value types when identity, invariants, secrecy or accidental mixing matter. Preserve enums/literals for closed vocabularies, free-form text and other documented primitive or serialization-boundary exceptions. Do not introduce a value object solely to wrap every scalar. The [Coding Standards skill](../SKILL.md) explains these conventions through contextual examples.

Read the current [action policy input](../../../../apps/backend/src/inframeld_backend/access/domain/policy_inputs/action_authorization_policy_input.py) and [action policy](../../../../apps/backend/src/inframeld_backend/access/domain/policies/action_authorization_policy.py) for exact declarations. The contract below explains how they compose shared eligibility without maintaining a second copy of their signatures here.

<a id="status-and-sources"></a>

## Status and sources

The broader utility default is an agreed coding preference for future suggestions and authorized changes. It does not claim that every existing helper has been migrated.

- [Canonical static utility convention](#static-utilities-and-mappers), [qualified policies](#qualified-policy-calls) and [component roles](component-roles-and-imports.md#component-conventions).
- Inspected examples: [ValueValidation](../../../../apps/backend/src/inframeld_backend/shared/domain/validation/value_validation.py), [PrincipalId](../../../../apps/backend/src/inframeld_backend/access/domain/value_objects/principal_id.py) and [ProjectUseOnlyGrantMapper](../../../../apps/backend/src/inframeld_backend/access/http/mappers/project_use_only_grant_mapper.py).
