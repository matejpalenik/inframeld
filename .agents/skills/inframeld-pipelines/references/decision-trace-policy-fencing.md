# PD-PIPELINES-02: Make a confirmed trace opt-out stop later capture and delivery

**Status:** PENDING

**Owner:** `inframeld-pipelines`

**Issue kind:** Implementation and privacy coordination contract.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Query A begins with recording on. Alice switches project tracing off while spans are buffered. She turns it on again before A finishes. A must keep answering normally, but its stopped capture must not restart or flush old buffers. Newly admitted Query B may record under the current policy.

The privacy outcome is accepted. Exact ordering/fencing at capture, persistence and delivery is not selected. A collector filter after sensitive capture cannot prove that a confirmed off result stopped stale workers or queued payloads.

## Accepted context and evidence

Installation categories and project preferences are distinct from inspection authority. Project opt-out suppresses both project-attributable categories. Re-enable applies to new eligible work, not an already suppressed execution. Already saved traces follow current access, retention and erasure.

Optional diagnostics failure cannot fail an otherwise healthy query or excuse missing required accounting, audit or receipts. A tracing delivery retry sends only already-captured still-permitted data and never reruns a model. Already handed-off external data cannot be recalled, but no later handoff may start after the effective restriction.

## Alternatives and trade-offs

1. **Use revisioned policy and execution-local suppression.** Capture eligible policy at admission, make stopped capture sticky for that execution and recheck current restrictions before persistence/delivery. This fits bounded queues, but the effective off acknowledgment needs a proven concurrent handoff boundary.
2. **Coordinate opt-out with an explicit bounded drain/barrier.** Establish the restriction, invalidate stale buffers and wait for a defined handoff boundary before confirming off. This makes acknowledgment meaning visible, but adds latency and failure/unknown outcomes.

## Non-binding recommendation

**Proposal only.** Prefer revisioned policy plus sticky per-execution suppression and the smallest proven acknowledgment barrier. Decide the actual capture/persist/deliver ordering together. Never claim off merely because a UI flag was saved.

## Decision trigger and stopping boundary

Before implementing trace capture/buffering/export delivery, opt-out acknowledgment or history-deletion fencing.

Pause unresolved coordination choices. Do not block ordinary query behavior on optional tracing or reopen the accepted privacy rule.

## Architectural impact and dependencies

Pipelines execution instrumentation, shared operational spans/queues, project policy commands, deletion/retention and CLI outcome representation. Update off/on and delivery-race sequences.

Load neighboring decisions only under these conditions:

- [PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure](../../inframeld-knowledge/references/decision-retention-erasure-policy.md). For retention and source-derived erasure.
- [PD-ACCESS-02: Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). Only when the underlying durable workload’s authority is affected.

## Open questions and required evidence

- What exact event makes off effective and when may success be acknowledged?
- How do stale workers and automatic instrumentation observe restrictions?
- How are uncertain persistence and already-in-flight delivery reported?
- How does source/history deletion prevent late resurrection?

## Sources and finalization

- [Trace lifecycle and coordination](query-tracing-and-privacy.md#trace-lifecycle).
- [Trace authority](query-tracing-and-privacy.md#trace-authority).
- [Diagnostic scope](../../../../docs/adr/ADR-0063-defer-product-non-query-diagnostic-browsing.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
