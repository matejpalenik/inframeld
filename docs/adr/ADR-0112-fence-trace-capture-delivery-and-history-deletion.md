# ADR-0112: Fence trace capture, delivery and history deletion

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

Tracing should help diagnose a query without becoming a second, uncontrolled copy of private data. A confirmed off action must affect running processes and queued writes, not just a settings screen.

## Considered Options

- Use the focused bounded contract above. Selected.
- Rely on a saved policy flag or collector filter alone, which cannot establish that stale capture/export stopped.

## Decision Outcome

Apply the [complete accepted PD-PIPELINES-02 contract](../../.agents/skills/inframeld-pipelines/references/decision-trace-policy-fencing.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use revisioned installation policy and Project preference with a monotonically changing recording epoch and execution-local sticky suppression. Record the eligible epoch at execution admission. An opt-out invalidates every older eligible execution for later project-attributable capture, persistence and delivery. Turning recording on admits new eligible executions only. Separate operational/workload switches, effective operator restrictions, exact human policy/deletion authority and independent trace inspection remain unchanged.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

The acknowledgment barrier adds bounded coordination and may report unconfirmed off during a broken runtime. This is preferable to falsely saying private capture stopped.

Alice switches recording off while Query A is running, then switches it on again. A keeps answering but never resumes capture. New Query B may record. Deleting A's history also blocks a late queued write from recreating it.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-pipelines/references/decision-trace-policy-fencing.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
