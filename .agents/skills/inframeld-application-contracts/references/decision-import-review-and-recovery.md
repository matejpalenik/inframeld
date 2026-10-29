# PD-CONTRACTS-04: Bind import review and partial recovery to exact actions

**Status:** PENDING

**Owner:** `inframeld-application-contracts`

**Issue kind:** Cross-module implementation contract.

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

Bob reviews an import that creates two resources and updates Pipeline revision 17. Alice saves revision 18 before the update executes. The creates may already have completed. Recovery must preserve them and require fresh review of the changed update, rather than overwriting 18 or reporting the entire import had no effects.

The preserve/apply rules and partial-outcome behavior are accepted. Exact equivalence checks, relevant destination revisions, parent/child identities, precondition ordering and recovery schemas remain open. Names or a generic confirmation cannot establish resource equivalence or authority.

## Accepted context and evidence

Import invokes owning operations in dependency order, preserves completed effects and never prunes omitted resources. New collections are empty, sources do not sync and no model/build/publication starts implicitly. Credentials remain separate, and protected policies retain human-only authority.

Bind the actual definitions and reviewed mappings, not merely a laptop path. Recheck relevant current state before effects and at each owner’s boundary. There is no global project transaction or blanket project revision. Shared connection changes can affect live connectivity even without publication.

## Alternatives and trade-offs

1. **Persist a reviewed action plan with stable child operations.** Store bounded supported definitions/mappings and original child identities so interruptions recover exact actions. This makes partial progress clear, but needs explicit plan limits and per-owner outcomes.
2. **Reconstruct pending actions from the original durable input and recorded outcomes.** Recompute only through stable equivalence/precondition rules, retaining completed identities. This can reduce stored derived plan data, but is harder to prove safe when destination state changes.

## Non-binding recommendation

**Proposal only.** Prefer a bounded durable reviewed plan with stable child identities and owner-specific expected state. Re-review changed unfinished actions rather than silently retargeting them. Preserve the existing partial-effects contract and avoid a generic provisioning engine.

## Decision trigger and stopping boundary

Before implementing import planning/equivalence, admission ordering, child operations or interrupted-import recovery.

Pause the affected review/recovery contract. Existing domain operations and explicit preserve/apply authority remain accepted.

## Architectural impact and dependencies

Shared CLI/import orchestration, all imported resource owners, budget/trace policy and configuration schemas. Update review-to-partial-recovery sequences without copying owner persistence into import.

Load neighboring decisions only under these conditions:

- [PD-CONTRACTS-02: Coordinate budget policy, reservations and uncertain settlement](decision-spending-coordination.md). Only for explicit budget apply.
- [PD-PIPELINES-02: Make a confirmed trace opt-out stop later capture and delivery](../../inframeld-pipelines/references/decision-trace-policy-fencing.md). Only for trace-policy apply.
- [PD-ACCESS-02 (accepted): Keep durable work and credential lifetime explicit](../../inframeld-access-models/references/decision-admitted-work-authority.md). When queued import continuation needs credential-lifetime semantics.

## Open questions and required evidence

- What exact supported content makes a dependency equivalent?
- Which relevant revisions invalidate review?
- What is recorded before any resource effects, and how is it bounded?
- How do completed children recover when their resource is now inaccessible?
- Which partial results can be disclosed under current authority?

## Sources and finalization

- [Durable import and recovery](configuration-import-recovery.md#import-recovery).
- [Original import identity](configuration-import-recovery.md#import-recovery).
- [Context and target contracts](http-mcp-and-generated-clients.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
