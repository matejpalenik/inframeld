# ADR-0110: Serialize release control with expected revisions

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

An automatic update is building while Alice switches Production to Manual and back to Automatic. Bob might promote, roll back or change the default route at the same time. Checking only the current mode could revive an old update's authority and overwrite a newer decision.

## Considered Options

- Use the focused bounded contract above. Selected.
- Use only conditional writes, requiring every competing path to reproduce the complete atomic predicates.

## Decision Outcome

Apply the [complete accepted PD-RELEASES-01 contract](../../.agents/skills/inframeld-releases/references/decision-deployment-state-and-concurrency.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use one complete bounded Deployment control snapshot and one common SQL coordination/save contract for all competing transitions. Serialize control writes through the relevant Deployment record in a short transaction, while retaining the caller's expected revision as a stale-decision check. A lock protects the write ordering. It does not authorize silently retrying a stale human decision against newer state.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Because all competing actions use the same gate and revision checks, none can slip around another's control decision. The cost is brief contention on the same Deployment. Pure conditional writes could also work, but every path would need equivalent complete predicates. Short serialization plus expected revisions is easier to audit for this single-server product. Locks are released before slow external work.

Update U1 captures control 10. Alice switches to Manual, advancing control to 11. She later enables Automatic with a fresh U2, advancing to 12. U1 finishes with its original 10 and cannot publish. If Bob changes serving state before Alice's reviewed command commits, her expected revision conflicts. She sees what changed before making a new decision.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-releases/references/decision-deployment-state-and-concurrency.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
