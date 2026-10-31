# Preserve test isolation and honest evidence

Alice sees a passing fast suite and wants to know whether grant persistence and Hydra verification work. The answer depends on which scenarios ran and which collaborators were real. Inspect the test configuration, fixture lifecycle and collected results before extending the claim.

## Existing environment boundaries

The [testing runbook](../../../../docs/development/guides/testing.md) owns commands, endpoint addresses, image/cache setup, flags and cleanup procedures. The [integration fixtures](../../../../apps/backend/tests/integration/conftest.py), [temporary database support](../../../../apps/backend/tests/support/postgres.py), [Compose graph](../../../../compose.test.yaml) and [wrapper](../../../../scripts/test-integration.sh) own implemented mechanics.

Fast host checks use local test configuration and skip service-dependent tests. The private integration wrapper uses the committed example configuration and explicit test endpoints/credentials, not the host's development database or secrets. The integration runner container mounts source/tests read-only and uses a locked environment. Its existing [guest runner](../../../../apps/backend/tests/support/integration_runner.py) performs readiness checks and migrations inside the isolated test graph. A request to explain a domain behavior does not authorize running that stack.

Application scenarios receive fresh temporary databases through the existing fixtures. Their migration and resource lifecycles are scoped to those databases. The raw-statement exception remains limited to CREATE/DROP in the existing PostgreSQL test support. Do not turn test isolation into a general permission for raw persistence statements or development migrations.

The integration graph publishes no host ports and exposes no container socket to the runner. Follow its private service addresses rather than recreating provider services on public host ports. Controlled provider collaborators in database tests and real provider services in native scenarios establish different boundaries.

### Maintained commands and diagnostic probes

Complete acceptance runs use maintained repository commands and their selected pinned configuration. Prefer workspace entry points and documented focused/manual routes. A `pnpm` alias may invoke the same shell, Python or Cargo command directly documented by the runbook. The spelling alone does not establish safety, and service-dependent behavior still needs its real test boundary.

Write regressions as repository-owned unit, contract or integration tests at the responsible layer. Run the focused behavior, relevant regression suite and required qualification, without reflexively repeating the broadest suite after each edit. Preserve actual required CI, provider and SDK profile coverage. A passing mock or filtered SDK run cannot replace those requirements.

A temporary diagnostic answers one unresolved question. State the hypothesis and what decision its result will change, use the assigned source/images/runtime, bound its lifetime and clean only positively owned resources. Classify the result as product behavior, maintained harness/configuration, diagnostic setup or unavailable runtime. Correcting a wrong import or inspection field does not demonstrate a product fix. A successful address-allocation probe does not establish complete login qualification.

Use a direct read-only engine inspection where sufficient. Diagnostics that start services need coordinated integration access. Do not replace a maintained acceptance route with a private orchestration script or a sequence of manually approved engine variants. If a recurring useful check is missing, add a small regression or focused option to the existing maintained runner within scope, then return to that route. Do not create a separate qualification platform.

### Keep harness repairs bounded

Ordinary feature work stays with existing workspace commands and repository-owned tests. An explicitly scoped infrastructure repair may change its owning runner or add a necessary small helper, but must return verification to a maintained entry point. This exception supplies no host-repair authority or permission to build a general execution platform. During delivery, first use [defect triage](../../inframeld-backlog-delivery/references/discovered-defects.md) to decide whether the repair belongs here or should be recorded separately.

Before a harness repair expands, identify the exact blocked acceptance, required safety/correctness property, smallest maintained change and regression test. Inspect existing lifecycle helpers first. A process-ownership defect may require careful repair, but it does not automatically justify another supervisor.

Apply Review's [maintainability bar](../../inframeld-review/references/scoring-and-report.md#apply-the-maintainability-bar) to the complete repair and its fixtures. A novel execution path or substantial embedded fixture program needs the same readability and failure review as maintained source. A low line count or a `pnpm` prefix alone does not establish a maintainable solution.

During coordinated delivery, pause dependent expansion for coordinator scope review when proposing a general executor, new supervision/IPC protocol, duplicate lifetime mechanism, cross-package infrastructure or a private controller required for ordinary workspace checks. Compare adapting an existing mechanism, a narrow local repair and a separately scoped supporting maintenance PR. Independently review material shared-harness plans in that workflow. Standalone work uses the actual task authorization and ordinary review/decision guidance. It needs no invented coordinator or repeated approval for an already authorized change. Keep legitimate safety requirements rather than optimizing line count.

Demonstrate changed orchestration decisions with controlled tests and affected real startup/cleanup compatibility through the maintained path. Small maintained fixture checks can precede expensive journeys. A probe remains partial evidence and must not spawn a cascade of new controllers or human approvals. If the correction exceeds the accepted boundary or remaining remediation allowance, preserve the checkpoint and stop dependent work.

Choose the smallest meaningful reproducer before broadening the setup. A real process/IPC lifetime defect may need an owned-child test with an actual connection, while signal-order decisions can be tested with controlled syscalls. Establish the relevant real lifecycle early. Do not force identifier reuse, signal unrelated sentinel processes or use pure mock success as native cleanup proof. Reassess the complete repair if its new fixtures start requiring their own substantial repairs. The [#237 case](../../inframeld-backlog-delivery/references/case-237-testing-repair.md) explains that distinction without prescribing its unfinished implementation.

For example, a Compose dynamic range can exclude the static gateway, with an allocation-order regression and the required full journey. That is repository test configuration. Changing VM network settings is host repair. A retained-process correction belongs in the maintained runner with lifetime/cancellation tests. Any proposed general process-management service needs its own demonstrated need and accepted scope.

During coordinated delivery, [gates and recovery](../../inframeld-backlog-delivery/references/gates-and-recovery.md#classify-failures-and-bound-remediation) owns retry counting, report failures and immediate stops. Its [host boundary](../../inframeld-backlog-delivery/references/gates-and-recovery.md#keep-delivery-out-of-host-repair) overrides broader Debug/Docker repair suggestions. Stop affected runtime work at that boundary. Independent authorized work may continue. Ordinary explanation requests authorize no machine recovery.

## Cleanup and resource lifetime

Run one local integration operation at a time because the harness uses a fixed private test project. Overlapping commands are unsupported, without runtime locking, reservations or worktree ownership. The public shell entrypoint delegates startup, testing and cleanup to the [host Python phase runner](../../../../apps/backend/tests/support/integration_process_runner.py). It requires the repository's Python 3.13 toolchain with `waitid`/`WNOWAIT`, retains the immediate leader through all group signalling, and never signals that numeric group after reaping or ownership loss. Bounded, checked process observations distinguish executable members from defunct ones. Observation errors and unresolved children remain incomplete shutdown. Manual start, test and stop commands remain available. CI steps execute sequentially on their job's isolated runner. The [runbook](../../../../docs/development/guides/testing.md#serial-integration-workflow) owns supported commands, bounded process-group shutdown and post-run checks.

Automatic teardown makes one cleanup attempt with a 60-second work budget, followed if necessary by five seconds after TERM and five after KILL. Timeout remains failure, preserves an existing nonzero result and does not establish that container-engine resources were removed. Report potentially incomplete cleanup and use the existing manual recovery command once the engine is responsive. Direct manual cleanup retains its existing behavior without this automatic deadline. Keep short test budgets private to the runner's callable test inputs and copied controlled drivers, without public timeout settings or another supervisor. Fixtures retain their own immediate child until signalling ends. Recorded descendant PIDs are observations, never permission for post-reap cleanup signals. Qualify actual macOS and Linux process behavior separately from the container-engine run.

Cleanup removes the project's labelled containers and networks, followed by the two explicitly named and ownership-labelled disposable TLS volumes. Cleanup failure remains failure. Named application/Kratos database volumes survive. Startup generates fresh fixture certificates before consumers start, while repeated tests against a running stack reuse its credentials. The runner rejects expired or incomplete public expiry metadata before waiting for services, and reports safe failure categories without reflecting upstream text. The [fixture TLS lifecycle](../../../../apps/backend/tests/fixtures/password-breaches/README.md) owns generation and expiry. Per-test temporary application databases are removed, while uniquely named Kratos identities can remain in the retained test volume. Do not describe teardown as deleting every test datum or use a broad volume prune.

Focused provider runs use the same private graph and readiness/migration path. The separate development-OAuth qualification uses its unique disposable project, volumes, image and test-only key. Its paired overrides fail closed when incomplete. Follow that documented path rather than starting or migrating an existing development installation. A local Podman result does not establish Docker CI execution.

Close clients, database resources and bounded subprocesses through the existing lifecycle helpers, including cancellation and log draining where applicable. A timeout or lost acknowledgment may occur after an effect. Cleanup/retry assertions must preserve the owning operation's meaning and budget rather than blindly repeating work.

## Interpret outcomes by what ran

| Observation | Supported conclusion |
| --- | --- |
| Fast suite passes while integrations are skipped | The executed fast checks passed, with service-dependent evidence still absent. |
| Database test passes with a controlled token verifier | That local persistent/application path passed for the supplied provider evidence. |
| Native Kratos/Hydra scenario passes | The named provider behavior passed in that test graph and configuration. |
| SDK fixture passes with synthetic collaborators | That SDK/HTTP-adapter scenario passed, without proving real grants or provider login. |
| Cleanup fails or a required case is absent | Report the failure or incomplete run, even if earlier assertions passed. |
| Documentation or a trial explains the expected test | Editorial/agent-guidance evidence, not application qualification. |

Use the repository's [status vocabulary](../../../../docs/development/documentation-maintenance.md#preserve-status-and-explain-evidence). Include artifact revisions, environment and failure-injection details for qualification work. Distinguish author-run, developer-reported and unrun evidence. Do not infer broad support from a test filename or a historical passing report.

Keep model-provider calls controlled in ordinary tests and SDK qualification. Contacting paid endpoints, issuing live credentials, modifying grants or dispatching external CI requires the task's actual authorization. Loading a skill does not supply it. Authorized disposable integration commands can perform their documented migrations without implying permission for existing environments.

The [test strategy](test-strategy.md) owns layer selection, and [SDK qualification](../../inframeld-sdks/references/shared-qualification.md) owns client-specific completeness and protocol assertions. Keep newly implemented layers and unrun platform/provider journeys explicit instead of presenting future design as a current test suite.

SDK verification reports native typing, model/capability checks, shared HTTP scenarios, archive construction and installed consumers separately. Validation provenance distinguishes generated model decoding from generated schema validation, parsed JSON and no validation. Nullable/bodyless fixtures establish capabilities, while real provider and persistence qualification remain separate. See [current hardening evidence](../../../../docs/development/reports/sdk-hardening-verification.md) before describing checks as executed or recommending issue closure.
