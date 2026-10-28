# Choose the test boundary that demonstrates the behavior

Alice changes grant handling. A controlled service test can demonstrate that current denial stops a write. To demonstrate that a failed commit leaves no persistent grant, she needs the real database boundary. The test's useful claim depends on what actually ran, not the directory name alone.

## Evidence by layer

| Layer | Useful evidence | Boundary it does not establish alone |
| --- | --- | --- |
| Domain/unit | State transitions, invariants and rejected values without external I/O | Actual persistence or provider behavior |
| Application/service unit | Authorization ordering, coordinated calls, error/replay decisions with controlled collaborators | PostgreSQL rollback, locks or real provider verification |
| HTTP/OpenAPI contract | Delivered shapes, native schema, error conversion and routing | Real business persistence when collaborators are doubles |
| PostgreSQL integration | Implemented queries, constraints, transaction rollback and concurrency against temporary databases | Real identity-provider behavior when verifiers are controlled |
| Real provider integration | Concrete Kratos/Hydra HTTP and SDK behavior within the private test graph | Every account UI, CLI lifecycle or deployment combination |
| SDK conformance | Generated operation/model behavior against native HTTP contracts and backend witnesses | Business journeys whose database/provider boundaries are replaced |

Use the smallest useful test for the changed decision, then add integration evidence for the affected real boundary. These are complementary checks. No fixed test-count ratio or coverage percentage replaces a meaningful denial, stale state, concurrent write, lost acknowledgment or recovery case.

## Choose cases from ownership and failures

Read the owning domain workflow for expected behavior and exact code/OpenAPI for delivered representations. Preserve current authorization, original operation meaning and external-effect uncertainty when relevant. A successful return type cannot establish that those checks happened in the right order.

The [grant service tests](../../../../apps/backend/tests/unit/access/application/services/test_project_grant_change_service.py) exercise controlled decisions and failures. The [grant PostgreSQL tests](../../../../apps/backend/tests/integration/access/test_project_grant_change_postgres.py) exercise the persistent boundary. The [bearer session database tests](../../../../apps/backend/tests/integration/access/test_human_bearer_session_postgres.py) use controlled provider results with real services/database, while [real Hydra tests](../../../../apps/backend/tests/integration/access/test_human_hydra_session.py) exercise actual provider tokens. Their scopes must remain distinguishable.

HTTP contract work also checks native OpenAPI drift and exact request/response behavior. For generated clients, follow [shared SDK qualification](../../inframeld-sdks/references/shared-qualification.md) rather than creating a second SDK strategy here. The unified gate is implemented, while actual platform execution and external branch-rule activation remain separate evidence.

## Native language checks and test doubles

Language checks complement observable behavior. TypeScript compilation can reject an invalid model expression, while runtime validation is needed for received JSON. Rust model/type checks and Python model probes have their own mechanics. Do not force identical exception classes or test syntax across languages to claim common behavior.

Use controlled collaborators when they isolate the decision under test. The [shared core](../../inframeld-coding-standards/references/testing-and-documentation.md) owns TDD. For backend Python, [Python Standards](../../inframeld-python-standards/references/testing-and-documentation.md) owns protocol doubles, typing, naming and complete contextual examples. Fixtures and framework callables retain their valid function exceptions. No source-layout or import-boundary enforcement suite is introduced by this strategy.

## What to run and report

Follow the existing [runbook](../../../../docs/development/guides/testing.md) and actual package/workflow commands. Fast host checks keep service-dependent integration tests skipped. The private integration wrapper enables its database/Kratos/Hydra scenarios in the existing collection. Inspect the selection and flags before saying a relevant boundary ran.

Report commands, artifacts/configuration and executed outcomes. Distinguish personally run results from inspected source, historical reports and pending checks. Formatting/type checks, a skipped integration collection and an accepted test design are not runtime qualification. [Isolation and evidence](isolation-and-evidence.md) explains the operational limits.

Backend implementation and HTTP foundations can be qualified before deferred Studio. The existing web package has no test script establishing a frontend suite. Provider browser-flow HTTP tests and SDK Chromium tests do not establish an implemented Inframeld account UI or complete browser-to-CLI login. A future product journey needs its actual components and scenarios.

Evaluation's benchmark/case-quality workflows remain under the [Evaluation skill](../../inframeld-evaluation/SKILL.md). Tests of Evaluation code still use ordinary repository testing conventions, but passing those tests is not calibration or model-quality evidence.

SDK conformance now uses ordinary Node feature tests and native drivers. The [SDK architecture map](../../../../packages/sdk-tools/docs/architecture.md) explains those development-tool boundaries. Filtered local SDK runs remain partial evidence, and complete verification cannot infer real database/provider behavior from HTTP fixtures.
