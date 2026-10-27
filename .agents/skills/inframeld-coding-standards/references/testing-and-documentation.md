# Test behavior and explain the contract

<a id="test-behavior-and-explain-the-contract"></a>

Alice adds a grant workflow. A useful test proves what happens when authority is missing or a response is lost. A test that only checks the service's filename would not protect either behavior. Documentation should explain the same useful boundaries to a new maintainer.

This reference owns scaffold-first TDD, test-code conventions and documentation. For choosing test layers, dependency isolation or interpreting verification evidence, conditionally use the [Testing skill](../../inframeld-testing/SKILL.md). Routine code work does not require loading that strategy.

<a id="behavioral-tdd"></a>

## Behavioral TDD

For new behavior and bug fixes, follow this sequence:

1. Establish only the public symbols, signatures and lifecycle shape needed to import and execute the test. This may be an application-owned interface, protocol, exception or minimal pass-through class/module. The scaffold is an API outline and implements none of the behavior under test.
2. Write the behavioral test against those symbols.
3. Run it and require failure for the expected behavioral reason. Import/collection errors mean the seam is incomplete. Add only the missing symbol/signature and rerun.
4. Implement the smallest real behavior. Run the focused test, then the relevant suite.
5. Refactor while tests remain green. Do not smuggle behavior into scaffolding or add interfaces for speculative future services.

Qualify new workflows through domain, service and persistence behavior. Type-compatible authorization does not prove ordering before disclosure or mutation. Test the actual boundary.

Mirror production roles in unit tests. Group integration tests by scenario with distinct filenames. Do not add architecture/import-boundary tests, dependency-rule fixtures, composition-root construction tests, naming checks or similar setup-enforcement tests. The developer guards organization manually.

Test Command/Query inputs retain those suffixes without DTO. Other public test-support transfer records use DTO. Cohesive scenario helpers may remain grouped, and fixtures may remain functions.

When qualifying generated code, check the actual proposed files with the existing backend Ruff rules and strict Pyright, alongside meaningful behavior tests. For isolated examples, adapt import/source roots without weakening the rules. A partial or in-memory check is not proof that the final files pass. Report checks actually run and any remaining diagnostics.

<a id="purpose-before-implementation-detail"></a>

## Purpose before implementation detail

Start class and method docstrings with a simple purpose and product context for a reader new to the codebase. Explain what the component does and why it exists before technical details. A brief example, such as Alice's recovery cleanup checklist, can clarify an unfamiliar concept.

Keep documentation compact and value-based. Preserve trust assumptions, result meaning, expected failures, non-obvious invariants, I/O/state changes and resource/transaction ownership where a maintainer would otherwise investigate.

For public methods, prioritize caller prerequisites and failures that change the caller's next action. Avoid repeating the class contract, internal algorithms or persistence fields unless they affect correct use. Ordinary exception propagation needs no explanation.

Protocols own shared behavioral contracts. Implementations add useful details without repetition. Explain what a DTO establishes or a value object validates when the declaration alone does not make it clear. Keep longer workflows in linked guides and useful adapter details on the adapter.

Use compact Google-style Args, Returns and Raises sections only when they add information beyond annotations and surrounding prose. Do not repeat annotated types or argument descriptions. Prefer removing repetition over enforcing a fixed length. Straightforward error subclasses need no individual boilerplate docstring.

<a id="examples-and-exceptions"></a>

## Examples and exceptions

Useful purpose-first wording includes “Open a phase gate - return 204 even when the flow is unknown.” Other examples are “Loads the current account status and project grants using the caller's transaction”, “Identifies the caller after authentication. Project permissions are checked separately”, and “Closes resources created before startup failed.”

Remove text that merely repeats a name, signature, decorator or obvious statement. Do not pursue blanket declaration coverage. Apply the same rule to tests, fixtures, helpers and modules. Preserve meaningful scenarios and unusual setup while omitting descriptions that repeat assertions or test names.

Use no semicolons or em dashes in prose, comments or docstrings. Use separate sentences or a normal hyphen.

<a id="group-logical-steps-within-python-functions"></a>

## Group logical steps within Python functions

Use one genuinely empty line between distinct logical steps so the reader can follow the function in small sections. Separate independent checks, selection or loading, final validation and returning a result. Keep closely related statements together, such as obtaining a binding and handling its absence.

Use judgment rather than inserting a blank line after every statement or block. Avoid multiple blank lines between steps, whitespace on empty lines and comments that only label each section. Review this grouping alongside normal formatter checks. These are backend Python conventions, not additional Rust or frontend standards.

**Formatting illustration:** the complete `_select_password_admission()` method inside [IdentityRecoveryNotificationService](../../../../apps/backend/src/inframeld_backend/access/application/services/identity_recovery_notification_service.py). The statements, signature and ordering are unchanged. This is a method excerpt, not a replacement module. Its imports, enclosing class and other helper methods remain in the linked source.

```python
    def _select_password_admission(
        self,
        evidence: IdentityRecoverySettingsEvidenceDTO,
        facts: IdentityRecoveryAssociationFactsDTO,
    ) -> IdentityRecoveryAdmissionDTO | None:
        settings = facts.settings_binding
        if settings is None:
            if evidence.source_recovery_flow_id is not None or facts.session_binding is not None:
                raise ConflictError(
                    "Password evidence requires an existing native settings association."
                )
            return None

        if settings.settings_flow_id != evidence.settings_flow_id:
            raise RuntimeError("The facts do not match the requested settings flow.")

        if (settings.identity, settings.session_id) != (evidence.identity, evidence.session_id):
            raise ConflictError("Password evidence does not match its native settings association.")

        admission = self._require_matching_admission(facts.settings_admission, evidence)

        if settings.operation_id != admission.operation_id:
            raise RuntimeError("The settings facts do not match their original admission.")

        if (
            evidence.source_recovery_flow_id is not None
            and evidence.source_recovery_flow_id != admission.event.flow_id
        ):
            raise ConflictError("Password evidence names a different original recovery.")

        self._require_version(facts)

        return admission
```

Obtaining `settings` and handling its absence form one step. Blank lines then distinguish the identity checks, admission selection, remaining checks and returned result without introducing more methods or comments.

<a id="worked-example-test-a-rejected-transition-without-mutation"></a>

## Worked example: test a rejected transition without mutation

**Situation.** Adding an already assigned action must not replace or downgrade it. Testing only the raised exception would miss a partial mutation.

**Decision and placement.** Put domain behavior tests under the production owner's mirrored unit-test roles. This selected test excerpt includes its existing constants and scenario helper, with the imports it needs:

**Inspected teaching excerpt:** the typed constants, membership helper and complete duplicate-rejection test from [apps/backend/tests/unit/access/domain/entities/test_project_membership.py](../../../../apps/backend/tests/unit/access/domain/entities/test_project_membership.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from dataclasses import replace
from uuid import UUID

import pytest

from inframeld_backend.access.domain.entities.project_action_grant import (
    ProjectActionGrant,
)
from inframeld_backend.access.domain.entities.project_membership import (
    ProjectMembership,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_grant_level import ProjectGrantLevel
from inframeld_backend.access.domain.errors.project_grant_errors import (
    ProjectGrantAlreadyExistsError,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId

ORGANIZATION = OrganizationId(UUID(int=1))
PROJECT = ProjectId(UUID(int=2))
RECIPIENT = PrincipalId(UUID(int=3))
ACTOR = PrincipalId(UUID(int=4))
ACTION = ActionId("create-access-groups")
EXISTING = ProjectActionGrant(PROJECT, RECIPIENT, ACTION, ProjectGrantLevel.USE_ONLY, None)

def membership(
    *,
    grants: tuple[ProjectActionGrant, ...] = (),
    kind: PrincipalKind = PrincipalKind.HUMAN,
) -> ProjectMembership:
    return ProjectMembership(
        organization_id=ORGANIZATION,
        project_id=PROJECT,
        principal_id=RECIPIENT,
        principal_kind=kind,
        grants=grants,
    )

@pytest.mark.parametrize("level", list(ProjectGrantLevel))
def test_existing_assignment_cannot_be_replaced_or_downgraded(
    level: ProjectGrantLevel,
) -> None:
    original = replace(EXISTING, level=level)
    member = membership(grants=(original,))
    with pytest.raises(ProjectGrantAlreadyExistsError):
        member.assign_use_only_grant(action_id=ACTION, assigned_by_principal_id=ACTOR)
    assert member.grants == (original,)
    assert member.grants[0] is original
    assert member.grants[0].level is level
    assert member.grants[0].assigned_by_principal_id is None
```

The excerpt includes its actual typed fixtures. It is a complete runnable selection of the existing test module, shown for teaching rather than as an instruction to duplicate the test. The helper remains a function because it is local scenario setup, not a public production conversion utility.

**Walkthrough and failure.** The test exercises both grant levels. It checks the rejection, exact existing child instance, level and historical attribution after the attempted change. Those assertions protect meaningful state preservation. The neighboring successful-transition test covers attributed addition. An inheritance or filename assertion would protect neither behavior.

<a id="worked-example-test-service-ordering-and-replay"></a>

## Worked example: test service ordering and replay

**Situation.** A saved grant result must not bypass revoked authority, and a new change must finish its required writes before commit.

**Decision and placement.** Use application service tests with explicit protocol doubles to control results and failures. These complete tests are excerpts from the existing service test module. Its `GrantScenario`, `COMMAND`, `ACCESS`, `AUTHORIZATION`, `CONTEXT`, `SAVED_RESULT`, `NEW_RESERVATION` and `PROJECT_ID` fixtures are defined in that same linked file. They are selected examples, not standalone test files:

**Inspected teaching excerpt:** the complete authorization-before-reservation test from [apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py](../../../../apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py). This is existing code for explanation, not replacement or insertion instructions.

```python
import pytest

from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ResourceNotFoundError,
)

@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [AccessDeniedError, ResourceNotFoundError])
async def test_denied_authorization_does_not_reserve_work(
    error_type: type[AccessDeniedError | ResourceNotFoundError],
) -> None:
    """Authorization failure must stop the workflow before any reservation."""
    scenario = GrantScenario()
    scenario.authorizer.error = error_type()
    with pytest.raises(error_type):
        await scenario.assign()
    assert scenario.idempotency.calls == 0
    assert scenario.memberships.calls == 0
    assert scenario.memberships.loads == 0
    assert scenario.events == ["fingerprint", "begin", "authorize", "rollback"]
```

**Inspected teaching excerpt:** the complete authorized replay and revoked-authority test from [apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py](../../../../apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from dataclasses import replace

import pytest

from inframeld_backend.access.application.services.project_grant_change_fingerprint_service import (
    ProjectGrantChangeFingerprintService,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import (
    OperationReplayKind,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)

@pytest.mark.asyncio
async def test_replay_rechecks_authorization_before_returning_saved_result() -> None:
    """A prior success cannot bypass changed authority on the next request."""
    scenario = GrantScenario()
    old_command = replace(COMMAND, expected_access_revision=0)
    first = await scenario.assign(old_command)
    assert first == SAVED_RESULT
    assert scenario.authorizer.last_request == (
        ACCESS,
        PROJECT_ID,
        RECIPIENT_ID,
        ACTION_ID,
    )
    expected_fingerprint = ProjectGrantChangeFingerprintService(
        RequestFingerprintService(RequestFingerprintKey(b"K" * 32))
    ).for_assign_use_only(old_command)
    assert scenario.idempotency.context is CONTEXT
    assert scenario.idempotency.access is ACCESS
    assert scenario.idempotency.authorization is AUTHORIZATION
    assert scenario.idempotency.fingerprint == expected_fingerprint
    assert scenario.idempotency.expected_kind is OperationReplayKind.SAFE_RESULT
    assert scenario.events == ["fingerprint", "begin", "authorize", "reserve", "commit"]
    assert scenario.memberships.calls == 0
    assert scenario.memberships.loads == 0
    scenario.authorizer.error = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await scenario.assign(old_command)
    assert scenario.authorizer.calls == 2
    assert scenario.idempotency.calls == 1
```

**Inspected teaching excerpt:** the complete new-assignment commit-order test from [apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py](../../../../apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py). This is existing code for explanation, not replacement or insertion instructions.

```python
from dataclasses import replace

import pytest

from inframeld_backend.access.domain.value_objects.project_id import ProjectId

@pytest.mark.asyncio
async def test_new_assignment_completes_before_transaction_commit() -> None:
    scenario = GrantScenario()
    scenario.authorizer.result = replace(AUTHORIZATION, project_id=ProjectId(PROJECT_ID.value))
    scenario.idempotency.result = NEW_RESERVATION
    result = await scenario.assign()
    assert result == replace(SAVED_RESULT, created=True)
    assert scenario.memberships.last_operation == NEW_RESERVATION.operation_id
    assert scenario.memberships.last_project_id is scenario.authorizer.result.project_id
    assert scenario.events == [
        "fingerprint",
        "begin",
        "authorize",
        "reserve",
        "load_membership",
        "write",
        "complete",
        "commit",
    ]
```

**Walkthrough.** The denial test proves there is no reservation, aggregate load or save. The replay test proves the original result returns after current authorization, without another load or write, and later revoked authority stops lookup. The new-work test checks the original operation identity and checked scope, then completion before commit. These observable interactions protect the security and atomicity contract rather than the service's private layout.

**Failures and alternatives.** Neighboring tests cover mismatched returned scope, stale revision, narrow domain-error translation and reservation/save/completion/commit failures. Unit doubles cannot prove actual PostgreSQL rollback, locking or concurrency. The existing integration scenarios exercise those boundaries and must be qualified for a real affected implementation. Do not present a unit test as database evidence.

<a id="worked-example-document-the-capability-once"></a>

## Worked example: document the capability once

**Situation.** A new maintainer needs to know whether a recovery-block read opens a session, what its boolean means and how missing installation metadata fails.

**Decision and placement.** The [complete protocol and explicit double](protocols-and-persistence.md#worked-example-add-a-capability-and-its-test-double) show both docstrings and declarations. The protocol owns caller prerequisites, current unreleased-block meaning and session/failure requirements. The [PostgreSQL implementation](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_identity_recovery_block_reader.py) adds its authoritative query and availability translation. It does not repeat the entire shared contract.

Keep `@abstractmethod`, explicit protocol inheritance and `@override` on real implementations and doubles. A fake may expose controls for failure and overdue responses because those are useful test scenarios. No docstring is needed merely to repeat an annotated argument type, obvious constructor or test name.

<a id="sources-and-status"></a>

## Sources and status

- [Canonical service-writing guide](services-and-use-cases.md#service-writing-guide) and [grant chain](services-and-use-cases.md#grant-command-flow) supply actual workflow boundaries.
- [Root guidance](../../../../AGENTS.md#behavioral-testing-and-documentation) makes this sequence mandatory. Loading a skill does not authorize file writes, test-database provisioning or paid calls.
- [Backend tool configuration](../../../../apps/backend/pyproject.toml) and [strict Pyright configuration](../../../../apps/backend/pyrightconfig.json) supply the current rules. Do not install dependencies or modify those configurations merely to make an isolated example pass.

<a id="contracts-and-useful-documentation"></a>

### Contracts and useful documentation

Operation and I/O contracts are explicit protocols. Required methods use `@abstractmethod`. Implementations and test doubles explicitly inherit their protocol and mark overrides with `@override`. Strict Pyright checks those contracts. Protocols normally describe behavior. `ProjectCommand` and `AuthorizedOperationScope` are the agreed exceptions for required fields, with explicit inheritance and concrete declarations. Do not add unrelated record-labeling protocols.

Keep class and method docstrings focused on what callers need to use the component correctly. Start with a simple purpose and add essential context, such as trusted inputs, result meaning, side effects or transaction ownership. For public methods, prioritize prerequisites and failures that change what the caller must do next. Put the shared contract on the protocol and useful implementation details on the adapter. Follow the compact [docstring guidance](#purpose-before-implementation-detail).

Use Google-style `Args`, `Returns` and `Raises` sections only when they add information beyond the signature and existing prose. Avoid repeating argument descriptions or the class contract. Internal algorithms, lists of persistence fields and ordinary exception propagation do not belong in the method contract unless they affect correct use. Longer workflow explanations belong in guides. There is no fixed length limit - keep essential safeguards and remove repetition.

Remove comments and docstrings that only repeat a name, signature, decorator, or obvious statement. A straightforward error subclass does not need its own docstring. Explain exceptions when the distinction affects handling, such as a dependency failure that does not establish whether retrying is safe. Keep useful test/fixture explanations, especially for unusual setup. There is no blanket requirement to document every declaration.

Before generating code, choose its owner, layer, role, destination, name, declaration style, and behavioral contract. Check its dependency direction and whether any documentation actually adds information. [AGENTS.md](../../../../AGENTS.md) makes these conventions mandatory for generated and suggested backend code.

<a id="keeping-the-code-understandable-and-verifying-the-boundaries"></a>

### Keeping the code understandable and verifying the boundaries

Use names from the domain, keep related behavior together, return explicit errors, and keep interfaces focused on a clear responsibility.

Use small functions where they improve readability, without a fixed line limit. Explain why consistency and security rules exist in comments and ADRs. Add another DTO only when it translates meaningfully between responsibilities.

Tests should demonstrate business behavior, not just that methods were called. Examples include:

| Scenario | Behavior to verify |
| --- | --- |
| A promotion uses an outdated deployment revision. | The stale promotion is rejected. |
| A materialization has not been published. | It is unavailable for serving. |
| An operation references a resource from another project. | The cross-project reference is denied. |
| A process restarts and retries publication. | Publication is not duplicated. |

The developer manually guards forbidden imports, dependency cycles, and repository organization, following the repository's setup-test policy. Do not add architecture/import-boundary tests, dependency-rule fixtures, or composition-root construction tests. Automated tests verify implemented product behavior, API contracts, and integrations.

Tests of database and search behavior must use real PostgreSQL and the Chroma server shipped with the product. Mocks alone cannot show that real constraints, simultaneous changes, and search operations behave correctly.

<a id="maintainer-checks"></a>

<a id="5-maintainer-checks"></a>

## Maintainer checks

| Scenario | Expected outcome |
| --- | --- |
| An HTTP route, MCP tool, and worker perform the same operation | They call the owning application behavior with verified context. |
| A read screen joins two domains | A purpose-built read projection may join data. It does not acquire write ownership. |
| A grant changes while work is queued | The operation performs the current checks required by its owner. |
| An external call times out | No long SQL transaction is held. The owning retry protocol decides what is safe. |
| An index becomes ready | Readiness alone never changes Deployment traffic. |
| A million-row corpus is selected | Use bounded queries and batches. Do not load an entire aggregate into memory. |
