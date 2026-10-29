# ADR-0118: Audit index health with explicit freshness and unknown outcomes

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

An index can lose a record without returning an error. Periodic checks can discover that omission, but a ready label or unchanged counter cannot discover it by itself.

## Considered Options

- Use the focused bounded contract above. Selected.
- Rely only on demand-time/returned-result checks, leaving silent omissions outside an explicit audit window.

## Decision Outcome

Apply the [complete accepted PD-INDEXING-02 contract](../../.agents/skills/inframeld-indexing/references/decision-health-observation.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use bounded periodic plus event-triggered Indexing verification with separately recorded scope and freshness. Inventory/identity/placement audits are due every 5 minutes, have a 2-minute execution deadline and maximum accepted successful observation age of 10 minutes. Full numerical/content-integrity audits are due every 12 hours, have a 30-minute deadline and maximum accepted successful age of 24 hours. Initial complete readiness verification supplies the initial evidence only for the checks it actually performed. Record trusted manifests, checked generation/shard set, counts/hashes, check kind, observed storage/health generation, start/completion and outcome. A health revision is a change counter, not a sensor or an assertion that every fault is instantly detectable.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Audits consume predictable reads and can temporarily block service when freshness cannot be proved. They give an explicit detection window without pretending every query verifies every vector.

Bob accidentally loses one vector that Alice's current query would never retrieve. The inventory audit detects the missing ID. If audits stop running, health becomes unknown after its freshness limit and affected serving stops.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-indexing/references/decision-health-observation.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
