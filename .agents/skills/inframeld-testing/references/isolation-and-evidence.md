# Preserve test isolation and honest evidence

Alice sees a passing fast suite and wants to know whether grant persistence and Hydra verification work. The answer depends on which scenarios ran and which collaborators were real. Inspect the test configuration, fixture lifecycle and collected results before extending the claim.

## Existing environment boundaries

The [testing runbook](../../../../docs/development/guides/testing.md) owns commands, endpoint addresses, image/cache setup, flags and cleanup procedures. The [integration fixtures](../../../../apps/backend/tests/integration/conftest.py), [temporary database support](../../../../apps/backend/tests/support/postgres.py), [Compose graph](../../../../compose.test.yaml) and [wrapper](../../../../scripts/test-integration.sh) own implemented mechanics.

Fast host checks use local test configuration and skip service-dependent tests. The private integration wrapper uses the committed example configuration and explicit test endpoints/credentials, not the host's development database or secrets. Its runner mounts source/tests read-only, uses a locked environment and performs readiness checks and migrations inside the isolated test graph. A request to explain a domain behavior does not authorize running that stack.

Application scenarios receive fresh temporary databases through the existing fixtures. Their migration and resource lifecycles are scoped to those databases. The raw-statement exception remains limited to CREATE/DROP in the existing PostgreSQL test support. Do not turn test isolation into a general permission for raw persistence statements or development migrations.

The integration graph publishes no host ports and exposes no container socket to the runner. Follow its private service addresses rather than recreating provider services on public host ports. Controlled provider collaborators in database tests and real provider services in native scenarios establish different boundaries.

## Cleanup and resource lifetime

Run one integration wrapper at a time because it manages the fixed test project. Cleanup removes only that project's labelled containers and networks and reports cleanup failure as failure. Named application/Kratos test volumes survive. Per-test temporary application databases are removed, while uniquely named Kratos identities can remain in the retained test volume. Do not describe teardown as deleting every test datum or use a broad volume prune.

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
