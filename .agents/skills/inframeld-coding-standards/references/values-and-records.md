# Give values their domain meaning

<a id="give-values-their-domain-meaning"></a>

Alice's project ID and Bob's principal ID are both UUIDs. Passing one in place of the other is still an error. Inframeld uses distinct runtime types so the mistake can be caught before a workflow checks existence, scope and authority.

<a id="choose-a-meaningful-type"></a>

## Choose a meaningful type

Use a dedicated value object when identity, invariants, secrecy or accidental mixing matter. Value objects express immutable meaning and validate their own invariants. Entities have stable identity and cohesive state. Do not introduce a wrapper just to make every field look alike.

Use application-owned enums or `Literal` types for closed vocabularies. Meaningful open values, such as identity authorities and subjects, need distinct types when mixing them would be harmful. Free-form text and vocabularies whose values are not yet defined may remain strings.

Parse and validate at HTTP, provider, configuration and persistence boundaries. Serialize back to primitives there. Preserve existing wire/database values and real ORM conversion. An annotation alone performs no runtime validation.

<a id="runtime-identifiers"></a>

## Runtime identifiers

UUID-backed `PrincipalId`, `ProjectId`, `OrganizationId` and `AccessGroupId` are distinct frozen, slotted dataclasses containing `value: UUID`. Constructors require a UUID. Equal UUIDs in different identifier classes do not produce equal identifiers. Do not replace these runtime objects with aliases or `NewType`.

Preserve existing valid UUID versions and zero values unless a separately accepted invariant changes that. Use bare `UUID` when the entity kind is genuinely unknown. Parse external input to a UUID before constructing the appropriate ID. Keep ORM columns mapped as UUIDs and wrap persistence results at the adapter boundary.

This is the existing complete `apps/backend/src/inframeld_backend/access/domain/value_objects/principal_id.py`, shown for explanation, not as a proposed replacement:

```python
from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation

@dataclass(frozen=True, slots=True)
class PrincipalId:
    """Identify one Principal using a UUID, independently of its existence."""

    value: UUID

    def __post_init__(self) -> None:
        ValueValidation.require_uuid(self.value)
```

Run the static checker to catch wrong-ID contracts. Types do not establish record existence, checked scope or permission. `RequestId` is UUID-backed request correlation. `OperationId` is an opaque nonblank string for operation correlation. Neither is authority.

Use `Principal` when a workflow needs ID, organization, kind and status together. Pass `PrincipalId` when only identity is needed. Principal equality and hashing follow its ID. Add lifecycle behavior only when a workflow needs it.

<a id="commands-queries-and-other-records"></a>

## Commands, queries and other records

Use standard `@dataclass(frozen=True, slots=True)` for Commands, Queries, DTOs, dedicated policy inputs and immutable value objects. Preserve entity-specific equality and secret-safe representations. Do not add custom record decorators, marker bases, empty protocols or generic DTO/value-object frameworks.

A Command describes a requested change. A Query describes a requested read. Other DTOs carry results, projections and caller/operation metadata. Dedicated `PolicyInput` records carry decision inputs. Create a named Command or Query only when useful. Direct typed parameters remain valid.

`ProjectActionFactsDTO` is a persistence read result despite “Facts” in its name. The service converts it to `ActionAuthorizationPolicyInput`. A policy can also consume an existing entity or typed parameters. Commands and Queries may validate their own input without I/O, but current authorization, state checks and execution remain with services and domain rules.

<a id="narrow-interface-exceptions-and-secrets"></a>

## Narrow interface exceptions and secrets

The agreed nominal `Command` base and field-based `ProjectCommand` and `AuthorizedOperationScope[ProjectScope]` contracts are narrow exceptions to record-classification restrictions. Concrete frozen records explicitly inherit these contracts and declare their own fields.

Use `AuthorizedOperationScope[ProjectId]` for project authorization. An optional project type, including `None`, is valid only for results supporting organization scope. Field protocols are not read-only interfaces. Never mutate context through them or add more interfaces merely to label records. Strict Pyright checks incompatible fields and implementations missing required fields.

Secret-safe values must hide contents in representations and validation errors. Keep unavoidable framework `Any` and casts local and documented. Dictionaries remain appropriate at ASGI, JSON/OpenAPI, configuration-framework and logging-serialization boundaries. Narrow them there instead of broadening application contracts.

<a id="worked-example-distinguish-identity-at-the-boundary"></a>

## Worked example: distinguish identity at the boundary

**Situation.** Alice's actor ID and Support's project ID may contain the same UUID bytes. Their meanings remain different. The complete `PrincipalId` declaration above supplies runtime distinction as well as a static type.

**Decision and placement.** Keep an identifier in its owner's domain `value_objects` module. Parse external text into a UUID before construction. The HTTP mapper then constructs `ProjectId(project_id)` and `PrincipalId(request.recipient_principal_id)` from already parsed UUIDs. PostgreSQL predicates unwrap `.value`, and returned UUIDs are wrapped when adapters construct domain results. See the [complete HTTP mapper](static-utilities-and-mappers.md#worked-example-map-an-http-request-without-doing-the-work).

**Failure and alternatives.** A raw string fails construction. Passing a `ProjectId` to a `PrincipalId` contract is a static error, and wrapping one ID object as another fails the runtime UUID check. Neither type establishes existence or authority. Free-form text stays a string, and a bare UUID remains appropriate when the entity kind is genuinely unknown. The wrong-ID distinction does not authorize rejecting valid UUID versions or the zero UUID.

<a id="worked-example-request-a-change-without-carrying-permission"></a>

## Worked example: request a change without carrying permission

**Situation.** The grant operation needs Bob's identity, the action and the permission revision Alice last saw. Those inputs need a meaningful name and local validation.

**Decision and placement.** Use a frozen, slotted Command under Access application commands. This complete module also shows the agreed nominal and field-interface exceptions:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/application/commands/assign_project_use_only_grant_command.py](../../../../apps/backend/src/inframeld_backend/access/application/commands/assign_project_use_only_grant_command.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.command import Command
from inframeld_backend.shared.application.protocols.project_command import ProjectCommand

@dataclass(frozen=True, slots=True)
class AssignProjectUseOnlyGrantCommand(Command, ProjectCommand):
    """Request a grant change - current authority and revision require fresh checks."""

    project_id: ProjectId
    recipient_principal_id: PrincipalId
    action_id: ActionId
    expected_access_revision: int

    def __post_init__(self) -> None:
        if type(self.expected_access_revision) is not int:
            raise TypeError("The expected access revision must be a whole number.")
        if self.expected_access_revision < 0:
            raise ValueError("The expected access revision cannot be negative.")
```

**Walkthrough.** The Command describes requested work. Its revision is an integer because this published counter already has a defined representation and local validation. The exact `int` check rejects booleans as well as other types, and the next check rejects negative values. This is a documented primitive choice, not a reason to wrap every scalar or remove useful value objects.

The service separately receives `AccessContextDTO` and `OperationAdmissionContextDTO`. Access carries the authenticated actor and complete authentication evidence. Operation context carries retry metadata. Current authorization returns checked scope. None of those roles belongs on this Command, and local revision validation does not check current state. See [the complete service signature and workflow](services-and-use-cases.md).

**Alternatives.** Use a Query for a useful named read input. Keep results, projections and contexts as DTOs. `ProjectActionFactsDTO` becomes policy input only when the application selects the values for that domain decision. Direct typed parameters are valid when a named input adds no value.

<a id="worked-example-carry-a-secret-safely"></a>

## Worked example: carry a secret safely

**Situation.** Browser verification needs an opaque cookie, but diagnostics must not print it.

**Decision and placement.** The application-owned credential value object validates its own local invariant and excludes the value from generated representations:

**Inspected teaching excerpt:** complete inspected module from [apps/backend/src/inframeld_backend/access/application/value_objects/browser_session_credential.py](../../../../apps/backend/src/inframeld_backend/access/application/value_objects/browser_session_credential.py). This is existing code for explanation, not replacement or insertion instructions.

```python
"""Carry an opaque browser credential only as far as the verification adapter."""

from dataclasses import dataclass, field

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation

@dataclass(frozen=True, slots=True)
class BrowserSessionCredential:
    """Hold an untrusted session secret, excluding its contents from representations."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if not self.value:
            raise ValueError("A session credential must be nonempty.")
```

**Walkthrough and failure.** The constructor rejects a non-string or an empty credential without including the secret in its message. `repr=False` protects generated representations. It cannot protect a caller that explicitly logs `.value`, which remains prohibited. This type carries an untrusted secret, not proof of identity.

Use the existing `PrincipalKind` and `PrincipalStatus` enums for their closed vocabularies. Preserve their database and wire values. Keep JSON dictionaries, framework values and legitimate free-form text at their documented boundaries rather than introducing a generic value-object framework.

<a id="record-roles-dto-policy-input-entity-and-value-object"></a>

### Record roles: DTO, policy input, entity, and value object

A dataclass is an implementation mechanism, not a record's architectural role. Use standard `@dataclass(frozen=True, slots=True)` for command/query inputs, other application DTOs, policy inputs, and immutable value objects. Do not add custom decorators, empty protocols, or generic record frameworks. Keep nominal Command classification and required-field interfaces limited to the agreed ADR-0066 exceptions. Dataclass annotations do not perform runtime validation. Value objects retain their explicit checks, and command/query inputs may validate their own input constraints.

| Implemented record | What it means |
| --- | --- |
| `VerifiedHumanIdentityDTO` | The provider verified this authority/subject pair. Local account admission remains to be checked. |
| `AccessContextDTO` | The authenticated caller's principal ID and required authentication evidence, without cached status or permissions. |
| `ProjectActionTargetDTO` | The exact project selected for authorization. No proof of existence or visibility. |
| `ProjectActionFactsDTO` | Stored project/account status, membership, and exact-grant existence returned by a reader. |
| `ActionAuthorizationPolicyInput` | The eligibility and grant values the action policy consumes. |
| `CommandContextDTO` | Trusted request and operation identities used in command diagnostics. |
| `Principal` | A local account snapshot whose entity identity remains its `PrincipalId`. |
| `PrincipalId` | A UUID belonging to the principal identifier type, without proof that an account exists. |

Only `PolicyInput` identifies a dedicated policy input record. The word "Facts" in `ProjectActionFactsDTO` describes the reader's data. Its DTO suffix makes its application boundary explicit. The service converts it into the policy input. Policies may also accept an existing entity or typed parameters directly: human admission consumes `PrincipalAccessPolicyInput`, and project visibility accepts status and membership parameters.

[`Principal`](../../../../apps/backend/src/inframeld_backend/access/domain/entities/principal.py) contains its ID, organization, kind, and status. Equality and hashing use only its ID. The identifiers and enums live in separate files without weakening that cohesive entity. Pass the entity when a rule needs its state together. Pass its ID when only identity is needed.

UUID IDs are frozen, slotted dataclasses wrapping a parsed UUID. Constructors reject raw strings, and equal UUIDs in different ID classes remain distinct. Preserve existing UUID versions and zero values. Parse and validate at external boundaries, then explicitly wrap/unwrap IDs at persistence and transport boundaries. Existence and authorization require their normal checks.

Identity authorities and subjects are separate value objects, grouped by `VerifiedHumanIdentityDTO` after provider verification. `BrowserSessionCredential` remains application-owned and hides its contents in representations and validation messages. Never log its explicit `.value`. `RequestId` and `OperationId` represent correlation, not authority.

<a id="sources-and-limits"></a>

## Sources and limits

- [Canonical component/value conventions](component-roles-and-imports.md#component-conventions) and [ADR-0066](../../../../docs/adr/ADR-0066-use-typed-operation-contexts-and-command-classification.md) own the accepted record exceptions.
- [Authentication evidence](../../inframeld-access-models/references/browser-sessions.md) explains why a typed context is not a permission snapshot. [Transactions](../../inframeld-application-contracts/references/transactions-jobs-and-idempotency.md) explain checked scope and idempotency.
