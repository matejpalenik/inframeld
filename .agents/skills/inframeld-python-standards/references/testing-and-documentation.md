# Test behavior and explain the contract

<a id="test-behavior-and-explain-the-contract"></a>

Alice adds a grant workflow. A useful test proves what happens when authority is missing or a response is lost. A test that only checks the service's filename would not protect either behavior. Documentation should explain the same useful boundaries to a new maintainer.

This reference owns Python test-code and docstring conventions. The [shared core](../../inframeld-coding-standards/references/testing-and-documentation.md) owns scaffold-first TDD and cross-language documentation rules. For choosing test layers, dependency isolation or interpreting verification evidence, conditionally use the [Testing skill](../../inframeld-testing/SKILL.md). Routine code work does not require loading that strategy.

<a id="behavioral-tdd"></a>

## Behavioral TDD

Follow the [shared behavioral sequence](../../inframeld-coding-standards/references/testing-and-documentation.md#behavioral-tdd), including an API-only scaffold, the intended behavioral failure and green refactoring. Use that sequence to distinguish missing scaffold seams from other errors that prevent test execution. Keep Python fixtures and protocol doubles explicit rather than adding speculative services.

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

The [shared intent and wording rule](../../inframeld-coding-standards/references/testing-and-documentation.md#purpose-before-implementation-detail) also applies to private Python helpers. For example, `_lock_and_authorize()` needs to explain the ordering that its name alone does not establish.

**Inspected teaching excerpt:** only the docstring of `ProjectMembershipChangeService._lock_and_authorize()` in [apps/backend/src/inframeld_backend/access/application/services/project_membership_change_service.py](../../../../apps/backend/src/inframeld_backend/access/application/services/project_membership_change_service.py). The enclosing method and its checks remain in the linked source. This is not a replacement method.

```python
"""Read membership and actor authority under the Project lock.

Establish current permission before recovering a receipt or making a change.
"""
```

The first sentence gives the purpose. The second preserves the reason for checking current authority before a saved receipt can be returned. A helper whose name and types already make its behavior obvious needs no filler docstring. Useful intent may fit in one sentence or need more context, without a mandatory sentence count.

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

**Situation.** A saved grant result must not bypass revoked authority, and a new change must commit its required effects together.

**Inspected teaching excerpt:** three complete tests selected from [apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py](../../../../apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py). This is an existing test-module excerpt, not a standalone or replacement file. That module defines `GrantScenario`, its typed fixtures and the names used in parameterized inputs. The selected tests use these imports:

```python
from dataclasses import replace

import pytest

from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "facts",
    [
        replace(MANAGEMENT, grant=replace(MANAGEMENT.grant, actor_can_grant_action=False)),
        replace(MANAGEMENT, grant=replace(MANAGEMENT.grant, has_pending_recovery=True)),
        replace(
            MANAGEMENT,
            grant=replace(MANAGEMENT.grant, actor=replace(ACTOR, status=PrincipalStatus.SUSPENDED)),
        ),
    ],
)
async def test_current_actor_denial_precedes_even_a_completed_receipt(
    facts: ProjectActionGrantManagementFactsDTO,
) -> None:
    scenario = GrantScenario()
    scenario.management.result = facts
    with pytest.raises(AccessDeniedError):
        await scenario.set()
    assert scenario.idempotency.calls == 0 and "read_result" not in scenario.events

@pytest.mark.asyncio
async def test_completed_put_replays_before_fresh_revision_recipient_or_handover_checks() -> None:
    scenario = GrantScenario()
    scenario.management.result = replace(
        MANAGEMENT,
        recipient_has_pending_recovery=True,
        recipient_has_coherent_identity=False,
        other_grantors=(),
        grant=replace(
            MANAGEMENT.grant,
            project_access_revision=99,
            recipient=None,
            recipient_is_project_member=False,
        ),
    )
    result = await scenario.set()
    assert result == ORIGINAL
    assert scenario.events == [
        "fingerprint",
        "begin",
        "management_facts",
        "reserve",
        "read_result",
        "commit",
    ]
    assert scenario.memberships.loads == 0 and scenario.results.saved is None

@pytest.mark.asyncio
@pytest.mark.parametrize("can_grant", [False, True])
async def test_new_full_assignment_saves_original_status_revision_and_receipt(
    can_grant: bool,
) -> None:
    scenario = GrantScenario()
    scenario.idempotency.result = NEW_RESERVATION
    result = await scenario.set(replace(SET_COMMAND, can_grant=can_grant))
    assert (result.can_grant, result.access_revision, result.changed, result.status_code) == (
        can_grant,
        8,
        True,
        201,
    )
    assert scenario.results.saved == (result, 7, None)
    assert scenario.events == [
        "fingerprint",
        "begin",
        "management_facts",
        "reserve",
        "load_membership",
        "write_action",
        "complete",
        "store_result",
        "commit",
    ]
    assert scenario.idempotency.lookup_authority == OperationLookupAuthority(
        OperationLookupAuthorityFamily.PROJECT_GRANT_READ, ACTION_ID
    )
```

The denial case establishes no reservation or original-result disclosure. The replay case supplies a changed revision and now-ineligible recipient, yet returns the original receipt after current actor authorization without loading or saving membership. The fresh case checks explicit true/false grant intent, original 201, exactly one revision increment and audit/completion/business-result storage before commit.

Neighboring tests cover stale revision, no-ops, departed-recipient removal, foreign application binding, last-grantor preservation and required-stage rollback. These are behavioral observations. Unit doubles do not establish actual database rollback, coordination or concurrency. The owning PostgreSQL tests supply those distinct boundaries.

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
