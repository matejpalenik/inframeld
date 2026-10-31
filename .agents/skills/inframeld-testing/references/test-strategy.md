# Choose the test boundary that demonstrates the behavior

Alice changes grant handling. A controlled service test can demonstrate that current denial stops a write. To demonstrate that a failed commit leaves no persistent grant, she needs the real database boundary. The test's useful claim depends on what actually ran, not the directory name alone.

## Evidence by layer

Classify a test on two axes. Its **scope** is the behavior and boundary it checks. Its **resources** are what it actually uses, such as memory, files, subprocesses, sockets or shared services. A narrow CLI test can launch a real binary. A browser test can use a synthetic backend. Neither the directory nor the word "unit" establishes isolation, speed or complete product coverage.

| Layer | Typical resources | Useful evidence | Boundary it does not establish alone |
| --- | --- | --- | --- |
| Domain/unit | In-process values and logic | State transitions, invariants and rejected values | Actual persistence or provider behavior |
| Application/service unit | Controlled collaborators | Authorization ordering, coordinated calls, error/replay decisions | PostgreSQL rollback, locks or real provider verification |
| HTTP/OpenAPI contract | In-process application or fixture HTTP server | Delivered shapes, native schema, error conversion and routing | Real business persistence when collaborators are doubles |
| Local component | Temporary files, actual CLI binary, subprocesses or loopback sockets | Real adapter, command, output or package behavior | A deployed service graph or an external provider journey |
| PostgreSQL integration | Real PostgreSQL and temporary migrated databases | Implemented queries, constraints, transaction rollback and concurrency | Real identity-provider behavior when verifiers are controlled |
| Real provider integration | Private Kratos/Hydra graph and relevant database fixtures | Concrete provider HTTP and SDK behavior | Every account UI, CLI lifecycle or deployment combination |
| SDK conformance | Native drivers, fixture backend and browser where selected | Generated operation/model behavior against native HTTP contracts and backend witnesses | Business journeys whose database/provider boundaries are replaced |
| Test/delivery infrastructure | Controlled faults and, where needed, real owned processes or files | Runner selection, lifecycle, evidence and failure handling | Agent instruction following or product behavior merely because a helper passed |
| Documentation/examples | Content parser, temporary content or the documented command | Valid links, examples and their specifically executed behavior | An unexecuted end-user journey |

Use the smallest useful test for the changed decision, then add integration evidence for the affected real boundary. These are complementary checks. No fixed test-count ratio or coverage percentage replaces a meaningful denial, stale state, concurrent write, lost acknowledgment or recovery case.

Keep existing domain and package ownership. Local component tests can remain beside their package's unit tests when that organization is useful, provided their resource needs and cleanup are clear. Use existing maintained selectors and commands rather than adding a tagging framework or moving files solely to make labels uniform. This table is a choice of boundaries, not a requirement to run every layer for every issue.

Keep numerous small behavioral tests when each protects a meaningful case and remains inexpensive to understand. Remove duplication only when the remaining tests preserve useful failure coverage and diagnostics. Shared fixtures should make setup clearer, not hide important scenario differences behind a general builder or test language. Apply tests to the behavior being delivered through TDD, without inventing suites for unrelated future product owners.

## Choose cases from ownership and failures

Read the owning domain workflow for expected behavior and exact code/OpenAPI for delivered representations. Preserve current authorization, original operation meaning and external-effect uncertainty when relevant. A successful return type cannot establish that those checks happened in the right order.

The [grant service tests](../../../../apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py) exercise controlled decisions and failures. The [grant PostgreSQL tests](../../../../apps/backend/tests/integration/access/test_project_grant_change_postgres.py) exercise the persistent boundary. The [bearer session database tests](../../../../apps/backend/tests/integration/access/test_human_bearer_session_postgres.py) use controlled provider results with real services/database, while [real Hydra tests](../../../../apps/backend/tests/integration/access/test_human_hydra_session.py) exercise actual provider tokens. Their scopes must remain distinguishable.

HTTP contract work also checks native OpenAPI drift and exact request/response behavior. For generated clients, follow [shared SDK qualification](../../inframeld-sdks/references/shared-qualification.md) rather than creating a second SDK strategy here. The unified gate is implemented, while actual platform execution and external branch-rule activation remain separate evidence.

## Native language checks and test doubles

Language checks complement observable behavior. TypeScript compilation can reject an invalid model expression, while runtime validation is needed for received JSON. Rust model/type checks and Python model probes have their own mechanics. Do not force identical exception classes or test syntax across languages to claim common behavior.

Use controlled collaborators when they isolate the decision under test. The [shared core](../../inframeld-coding-standards/references/testing-and-documentation.md) owns TDD. For backend Python, [Python Standards](../../inframeld-python-standards/references/testing-and-documentation.md) owns protocol doubles, typing, naming and complete contextual examples. Fixtures and framework callables retain their valid function exceptions. No source-layout or import-boundary enforcement suite is introduced by this strategy.

### Check the claim independently

An **oracle** is how a test decides whether the result is correct. Prefer an observable result, persisted state or independently recorded request for the claim under test. Computing the expected result through the same production transformation can repeat its mistake. Reusing that transformation for incidental setup is different when its correctness is covered at its own boundary. Real collaborators are useful when cheap and isolated. Doubles remain useful for controlled decisions, remote boundaries and hard-to-reproduce failures.

For example, Alice tests a consent request with `decision: deny`. The generated client's successful return alone cannot prove it sent `deny`. The backend [HTTP witness](../../../../apps/backend/tests/unit/contract/test_sdk_conformance_app.py) independently records the received request. Pair the intended case with a relevant wrong value or missing field so the test can distinguish the defect. Use focused negative cases where they improve confidence, without building a mutation-testing platform for every test.

Assert call order when order is behavior, such as authorization before disclosure or reservation and saving an audit event before commit. Prefer meaningful values and effects over incidental object identity, private helper calls or a complete internal call transcript. A harmless refactor should not fail a test unless it changes a protected contract. Exact output assertions remain appropriate for public CLI formats and wire contracts.

### Match a helper test to a real boundary

Alice's deadline test makes an unresolved promise reject. It demonstrates bounded waiting. It does not demonstrate cancellation of the underlying work or that Chromium, a child process, sockets and logs have closed. Use controlled tests for deadline or signal-order decisions and a small real lifecycle regression for changed operating-system or browser behavior. Keep those separate claims in reports. Actual platform qualification still follows the owning maintained route.

A failing test identifies a mismatch to investigate. Check the accepted behavior and whether setup, the expected result or the implementation is wrong before changing production code. An import failure is not the intended behavioral red test. TDD sequencing remains owned by the shared core.

## What to run and report

Follow the existing [runbook](../../../../docs/development/guides/testing.md) and actual package/workflow commands. Fast host checks keep service-dependent integration tests skipped. The private integration wrapper enables its database/Kratos/Hydra scenarios in the existing collection. Inspect the selection and flags before saying a relevant boundary ran.

Report commands, artifacts/configuration and executed outcomes. Distinguish personally run results from inspected source, historical reports and pending checks. Formatting/type checks, a skipped integration collection and an accepted test design are not runtime qualification. [Isolation and evidence](isolation-and-evidence.md) explains the operational limits.

CI selects complete check families through the [shared relevance policy](../../../../docs/development/guides/testing.md#ci-selection). A successful not-applicable check records a selection decision, not an executed application test. Inspect selected jobs and their actual results before claiming qualification. Local complete commands and the SDK evidence requirements retain their existing meaning.

The [CI cache policy](../../../../docs/development/guides/testing.md#ci-dependency-caches) permits dependency reuse and exactly pinned tools while keeping selected checks and evidence fresh. Cache hits do not establish a passing test, audit or packaging result. Keep workspace artifacts, qualification outputs and integration state outside caches. Report observed cold/warm behavior separately from local validation.

Backend implementation and HTTP foundations can be qualified before deferred Studio. The existing web package has no test script establishing a frontend suite. Provider browser-flow HTTP tests and SDK Chromium tests do not establish an implemented Inframeld account UI or complete browser-to-CLI login. A future product journey needs its actual components and scenarios.

Evaluation's benchmark/case-quality workflows remain under the [Evaluation skill](../../inframeld-evaluation/SKILL.md). Tests of Evaluation code still use ordinary repository testing conventions, but passing those tests is not calibration or model-quality evidence.

SDK conformance now uses ordinary Node feature tests and native drivers. The [SDK architecture map](../../../../packages/sdk-tools/docs/architecture.md) explains those development-tool boundaries. Filtered local SDK runs remain partial evidence, and complete verification cannot infer real database/provider behavior from HTTP fixtures.

## Supporting guidance

[Software Engineering at Google, testing overview](https://abseil.io/resources/swe-book/html/ch11.html) explains scope, resource size and isolation. Its [unit testing](https://abseil.io/resources/swe-book/html/ch12.html) and [test doubles](https://abseil.io/resources/swe-book/html/ch13.html) chapters inform readable behavioral assertions and collaborator fidelity. Apply those principles to the repository's existing boundaries, without importing a universal suite ratio or another framework.
