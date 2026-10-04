# Definition of Done

This is the shared completion contract for implementation tickets. A ticket adds its own behavioral acceptance scenarios; this document does not replace them. Planning edits and accepted decisions are not runtime evidence.

1. **Behavior is demonstrated.** Run focused behavioral tests at the responsible layer. Where relevant, include denied access, changed permissions, stale revisions, competing writers, lost acknowledgments and bounded recovery. Record the commands and results actually observed, separately from pending checks. Do not add architecture or naming-enforcement tests.
2. **Ownership remains clear.** Follow the existing domain, application and adapter boundaries. Application and domain contracts use application-owned types, not HTTP, ORM or vendor SDK types. No new service, workflow engine or generic framework is introduced merely to deliver a ticket.
3. **Public contracts agree.** For externally observable HTTP changes, update the backend-owned native OpenAPI contract and its focused contract tests. Generated clients, CLI and future Studio consume that contract; MCP shares application behavior where its accepted tools expose it. Never weaken authorization or errors to accommodate a generator.
4. **Failure is safe and understandable.** Preserve current authorization, secret-safe output, bounded resources, durable operation identity and honest partial/uncertain outcomes. Test applicable external-call and transaction boundaries rather than claiming exactly-once provider execution.
5. **Documentation stays authoritative.** Update the owning guide, affected records, ADR and skill route when their contract changes. Reconcile a discovered architectural discrepancy before continuing; distinguish accepted design from implementation and measured qualification.
6. **Scope stays explicit.** Meet the ticket's acceptance scenarios and exclusions within Apache-2.0, the single-server Compose architecture and the existing backend. Do not silently expand permissions, deployment topology, release authority or supported platforms.

Qualification tickets additionally record the tested artifact revisions, environment, failure-injection method, results and limitations. A failing gate remains open; documenting the intended test is not passing it. Completed historical tickets are not reopened solely because this template was adopted.

See [the delivery plan](cli-delivery-plan.md) for issue ownership and [documentation maintenance](documentation-maintenance.md) for keeping specifications consistent.
