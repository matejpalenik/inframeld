# Assess the behavior and the cost of maintaining it

Alice will debug this code after its original author has forgotten the details. A useful review asks whether she can locate the owner, understand why each safeguard exists and change one behavior without rediscovering a framework. This reference owns the questions used by the review process. It does not replace language or domain standards.

Read the sections affected by the requested change. A complete feature review considers every lens, while a narrow review need not inspect unrelated infrastructure. Record meaningful gaps rather than filling them with assumptions.

| Concern | Reading route |
| --- | --- |
| Can a person follow and change it? | [Maintainability](#human-maintainability-and-language-standards) |
| Is the complexity necessary? | [Proportionality](#present-need-and-overengineering) |
| Are the boundaries and state safe? | [Correctness and architecture](#correctness-data-integrity-and-architecture) |
| Can it grow without building the future now? | [Scale and resources](#scalability-performance-and-future-evolution) |
| Are trust and protected facts preserved? | [Security](#security-privacy-and-dependencies) |
| Do tests prove anything useful? | [Tests and their harness](#test-value-and-harness-cost) |
| Can developers and operators use it? | [Experience and operations](#developer-and-operator-experience) |

## Human maintainability and language standards

Follow the user journey into the public entry point, operation, decision and external adapter. Can a new reader predict where the next component belongs? Are names about product meaning and responsibility? Are resource ownership, significant state and external effects visible? Does a changed rule have one owner, or must several copies be found and kept aligned?

Review the cost of a likely modification, such as adding one argument, changing a trust rule or diagnosing a rejected operation. Look for concrete reasons a change spreads across unrelated files. A large cohesive file can be easier to maintain than many forwarding modules. Conversely, unrelated policies and I/O in one file can conceal different reasons to change. Size is a signal to investigate, not a finding by itself.

Can a maintainer follow the normal operation and one relevant failure without reverse-engineering a private framework? Check explicit state transitions, resource ownership, readable control flow, native types and preserved errors. Hidden global coupling, duplicated business rules, unexplained fallbacks and substantial programs embedded in shell or string literals need a concrete reason. Prefer ordinary maintained source for nontrivial fixture programs. A small subprocess snippet, documented shell wrapper or necessary adapter is not inherently a defect.

Apply the affected language skill's mandatory declarations, imports, typing and documentation rules. Rust functions, modules and resource-owning structs need not resemble Python services. Generated code remains generator-owned. Documented exceptions count as valid practice rather than violations to remove.

Read meaningful rustdoc, docstrings and examples as contracts. They should explain purpose, effects, ownership, relevant failures and what a result establishes. Flag misleading guarantees, stale source links and unqualified examples when they can misdirect a maintainer. Do not ask for boilerplate on obvious helpers or a second architecture manual in every file.

## Present need and overengineering

For each substantial abstraction, dependency, state store, coordinator or lifecycle, identify the supported behavior that requires it. What specific failure does it prevent? How often can that failure occur in the supported workflow? What new failure, configuration, upgrade and recovery obligations does the mechanism introduce? Compare that cost with the smallest safe alternative.

A custom trait can protect a genuine boundary with one implementation. A lock can protect a real supported race. A wrapper can enforce a meaningful invariant. None needs several implementations merely to earn its existence. Equally, imagined future backends, users or deployment modes do not justify generic registries, plugin systems, command buses or distributed coordination now.

Do not equate DRY with removing all repeated text. Sharing a real rule prevents drift. Combining different trust decisions or forcing unrelated commands through one executor can make them harder to understand. Small local duplication can be cheaper until the meanings genuinely converge.

A finding about unnecessary complexity must name the component, the absent or disproportional need, its maintenance cost and a simpler alternative with preserved invariants. Vague suggestions to simplify, add layers or use a familiar pattern are not actionable. Do not call known required safety overengineering merely because its implementation takes code.

When a repair expands or its replacement needs substantial corrections, assess the accumulated change against main, including its test fixtures, supervision and new failure modes. A good score for the latest small patch or a process-only slice does not rate the whole solution. Identify the reviewed boundary and remaining qualification explicitly. For coordinated delivery, [defect triage](../../inframeld-backlog-delivery/references/discovered-defects.md) owns the decision to separate, defer or park the newly discovered work. Do not restart unrelated audits after routine corrections.

Apply the [maintainability bar](scoring-and-report.md#apply-the-maintainability-bar) before endorsing further expansion. A new executor, supervisor, IPC protocol, store or alternative verification path needs a demonstrated present limitation and comparison with the existing maintained mechanism. If the explanation remains hypothetical or the added machinery is disproportionate, return Changes needed and stop dependent expansion. A remaining retry allowance does not authorize complexity. Keep the failure, evidence, smallest alternative and unblock condition in the existing review or assignment record.

For example, a feature test failure does not justify a private Bash controller that recreates services and bypasses the workspace command. A focused regression in the responsible package is usually the useful next step. An actual process-ownership defect can justify a narrowly reviewed lifecycle helper, with its own real failure test. Review the complete resulting repair rather than assuming either all shell is bad or all safety-related machinery is necessary.

## Correctness, data integrity and architecture

Trace supplied input to the actual effect, including representation changes, validation, checked scope and returned facts. Check empty/absent/unknown distinctions, boundary values and supported malformed input. Use contracts rather than guessing meaning from a name. For externally observable changes, verify callers, native OpenAPI, generated consumers and applicable compatibility obligations agree.

Locate the authoritative state and each writer. Inspect the affected transaction, audit, idempotency and retry boundaries. Consider failed validation, rejected authority, stale observations, duplicate requests, lost acknowledgments and partial cleanup where they can occur. A timeout does not establish that a remote write did not happen. Keep actual concurrency safeguards even when local development is sequential.

Use [state and failure boundaries](state-and-failure-boundaries.md) only for affected state, concurrency, external-effect or recovery paths. Its questions locate evidence for existing contracts. They do not create new feature dependencies or production guarantees.

Check whether commands, HTTP routes and jobs invoke the same owning behavior rather than independently reproducing permissions or persistence. Review dependency direction and lifecycle ownership manually. Do not invent an aggregate, repository or service for a simple projection merely to fill a diagram.

Tie the finding to the affected operation. Do not demand a full multi-tenant, event-driven or highly available architecture from an unrelated helper. Conversely, the single-host deployment constraint does not excuse corrupted durable state, credential leakage or missing authorization.

## Scalability, performance and future evolution

Start with supported input sizes, workload, resource budgets and actual measured evidence. If these are unknown, state that limitation. Inspect likely bottlenecks such as unbounded reads, repeated queries, expensive work on a request path, blocked event loops, uncontrolled fan-out and missing admission or cleanup bounds. Request measurements when they would change a material decision. Do not invent throughput numbers or add caches before identifying a bottleneck.

Separate three judgments: adequate for the current supported deployment, a plausible path to a larger workload, and a distributed deployment actually implemented and tested. A clean interface proves neither horizontal scaling nor Kubernetes readiness.

Review expensive future constraints at their real boundary: durable identifiers, public contracts, data ownership, process-local authoritative state, storage assumptions and side-effect coordination. Identify what would have to change if the API or worker were replicated. Explain the migration trigger and likely cost where it matters. Do not implement that migration during review or block V1 solely because it still uses local volumes and Compose service addresses.

Prefer documented deployment assumptions and cohesive ownership to speculative portability frameworks. Valid V1 decisions can need replacement later. Preserve room to evolve without promising that arbitrary future deployment modes will be effortless.

## Security, privacy and dependencies

At affected trust boundaries, follow identity, current permission, resource scope, credentials and protected data separately. Check disclosure before authorization, credential forwarding, injection, unsafe destinations, redirects, filesystem escapes and secret-bearing errors or logs when relevant. Consider what a caller or dependency controls and which response is genuinely trusted.

Review configuration validation, defaults, exposed endpoints, dependency capabilities, licenses and existing audit exceptions within scope. Read an accepted exception's rationale before calling it an unfixed blocker. Reassess it when its usage or dependency evidence changes. A waived advisory is not a patched dependency, and passing an audit is not proof of application security.

Use current primary documentation when a version-specific external capability affects a finding. Do not print secrets or contact production services to demonstrate a hypothesis. Missing scope or evidence limits the review. It does not justify a blanket security score or a generic compliance checklist for code that does not touch that boundary.

## Test value and harness cost

For a meaningful test, identify the invariant or user-visible contract and the regression it would catch. Look for independent expected behavior rather than expectations derived from the implementation itself. Check that rejection also prevents an unwanted effect or disclosure when that distinction matters. Consider valid alternatives so a negative test does not pass for the wrong reason.

Distinguish observations from their proof boundary. Controlled unit collaborators can demonstrate decisions and ordering, not real database rollback or provider behavior. Integration tests should exercise the relevant real boundary. Shared SDK agreement needs independent request/response evidence. Use the [Testing skill](../../inframeld-testing/SKILL.md) for layer selection and evidence, rather than copying its complete procedure here.

String and filesystem assertions are not inherently weak. Exact CLI output, JSON shape, secret exclusion, archive content, installation behavior and absence of unintended credential files can be real contracts. Tests of source wording, module names or the mere presence of repository files usually protect organization rather than product behavior and conflict with the existing setup-test policy. Determine the assertion's purpose before recommending deletion.

Assess test execution time, determinism, isolation, cleanup, diagnostic usefulness and maintenance cost. Use observed timings and flakiness. Do not add retries, broad timeout increases, parallel execution or a second qualification suite merely to appear thorough. A sequential developer/CI harness does not need worktree leases or a scheduler unless a supported overlapping operation is demonstrated. Production concurrency is a separate concern.

Review the harness as production tooling with its own failure paths, but keep its guarantees proportional to the trusted commands and supported environment. Reuse existing commands and fixtures. Recommend a new framework or dependency only when a repeated, concrete limitation warrants it. Test count and coverage percentage alone do not establish test quality.

## Developer and operator experience

Try to follow the documented setup, invocation, failure explanation and recovery route. Are commands predictable, errors actionable and outputs suitable for their actual consumers? Check streams, exit status, noninteractive behavior and machine output when implemented. Do not invent CLI commands, JSON modes or guarantees deferred to another issue.

For lifecycle changes, inspect startup failure, shutdown, cancellation, timeouts and partial effects. Review persistent versus disposable state, compatibility, upgrades and rollback where the change affects them. Diagnostics should distinguish a failed observation from a completed action and avoid exposing protected input. Observability should answer actual operational questions rather than create another telemetry platform.

Check the manual verification recipe required by [CLI guidance](../../../../apps/cli/AGENTS.md#manual-feature-verification) for user-facing CLI work. Record whether it was run and its prerequisites. For library-only delivery, explain what users can inspect today and what remains unexposed. Documentation should make honest developer use possible without treating automated tests as a manual journey.

## Sources for proportionality

[Google's review guidance](https://google.github.io/eng-practices/review/reviewer/looking-for.html) motivates inspecting human comprehension and present need. [YAGNI](https://martinfowler.com/bliki/Yagni.html) distinguishes speculative capabilities from useful refactoring and tests. [SRE troubleshooting](https://sre.google/sre-book/effective-troubleshooting/) motivates observations and testable hypotheses before corrective expansion. These inform review questions. Repository contracts and the explicit maintainability bar own requirements.

## Owners and limits

[Coding Standards](../../inframeld-coding-standards/SKILL.md) and its language siblings own code conventions. [Application Contracts](../../inframeld-application-contracts/SKILL.md) and domain skills own behavior. [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md) owns current product boundaries. These lenses support a scoped engineering judgment, not an exhaustive security audit, capacity benchmark or production certification.
