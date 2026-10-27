# Definition of Done

<a id="definition-of-done"></a>

This is the shared completion contract for implementation tickets. A ticket adds its own behavioral acceptance scenarios. This document does not replace them. Planning edits and accepted decisions are not runtime evidence.

1. **Behavior is demonstrated.** Run focused behavioral tests at the responsible layer. Use [Testing](../../.agents/skills/inframeld-testing/SKILL.md) when choosing layers, isolation or interpreting evidence. Coding Standards retains test-code conventions and scaffold-first TDD. Where relevant, include denied access, changed permissions, stale revisions, competing writers, lost acknowledgments and bounded recovery. Record the commands and results actually observed, separately from pending checks. Do not add architecture or naming-enforcement tests.
2. **Ownership remains clear.** Follow the existing domain, application and adapter boundaries. Application and domain contracts use application-owned types, not HTTP, ORM or vendor SDK types. No new service, workflow engine or generic framework is introduced merely to deliver a ticket.
3. **Public contracts agree.** For externally observable HTTP changes, update the backend-owned native OpenAPI contract and its focused contract tests. Generated clients, CLI and future Studio consume that contract. MCP shares application behavior where its accepted tools expose it. Never weaken authorization or errors to accommodate a generator.
4. **Failure is safe and understandable.** Preserve current authorization, secret-safe output, bounded resources, durable operation identity and honest partial/uncertain outcomes. Test applicable external-call and transaction boundaries rather than claiming exactly-once provider execution.
5. **Documentation stays authoritative.** Update the owning workflow/record references, affected guidance, ADR and skill route when their contract changes. Reconcile a discovered architectural discrepancy before continuing. Distinguish accepted design from implementation and measured qualification.
6. **Scope stays explicit.** Meet the ticket's acceptance scenarios and exclusions within Apache-2.0, the single-server Compose architecture and the existing backend. Do not silently expand permissions, deployment topology, release authority or supported platforms.

Qualification tickets additionally record the tested artifact revisions, environment, failure-injection method, results and limitations. A failing gate remains open. Documenting the intended test is not passing it. Completed historical tickets are not reopened solely because this template was adopted.

For SDK-affecting HTTP changes, follow the [shared endpoint and conformance workflow](../../.agents/skills/inframeld-sdks/references/shared-qualification.md). [ADR-0090](../adr/ADR-0090-qualify-sdks-with-shared-contract-scenarios.md) accepts scenarios and native bindings for every delivered operation, with required checks for selected SDKs. The unified SDK runner and operation-coverage gate are implemented. Automatic Linux checks cover applicable PRs, with macOS for generator and platform-sensitive process/browser/lifecycle changes, plus manual runs. Report actual platform execution separately, and configure external branch rules to require the SDK conformance aggregate.

Use the [endpoint walkthrough](../../packages/sdk-tools/docs/adding-endpoint.md) to keep shared inputs and assertions beside each other. After explicit regeneration, run complete `pnpm sdk:verify`. Profile/case-filtered runs are partial local evidence. Review changed fields, exact status, native model constraints and independent backend observations even when operation coverage already passes.

See [V1 scope](../../.agents/skills/inframeld-architecture/references/v1-scope-and-extension-boundaries.md) for accepted delivery boundaries and [documentation maintenance](documentation-maintenance.md) for keeping specifications consistent.

SDK verification also requires strict native driver/consumer typing, operation-specific response assertions, absence/null fidelity, case-scoped witnesses, lifecycle/resource checks, archive builds and actual installed-consumer requests. Use the [hardening evidence](reports/sdk-hardening-verification.md) to distinguish local execution, applicable pending CI, independent review and pending upgrades before recommending issue closure.

For response or transport changes, retain positive and negative status/media cases, honest failure types and native default-constructor/override checks. [ADR-0094](../adr/ADR-0094-select-sdk-response-variants-and-safe-transport-defaults.md) and [subsequent verification](reports/sdk-response-fixes-verification.md) record the current behavior without broadening publication or compatibility promises.
