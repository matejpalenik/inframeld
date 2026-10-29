# ADR-0121: Qualify a small single-host operating envelope

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

Several individually bounded jobs can still exhaust one shared host. One conservative whole-installation profile gives every owner the same budget.

## Considered Options

- Use the focused bounded contract above. Selected.
- Qualify the larger 25k-document planning workload first, increasing cost and delaying a supportable initial profile.

## Decision Outcome

Apply the [complete accepted PD-ARCHITECTURE-01 contract](../../.agents/skills/inframeld-architecture/references/decision-supported-operating-envelope.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Select the existing 16-vCPU/64 GiB RAM/1 TB usable SSD or NVMe single-host Docker Compose installation as the first qualification target, with remote generation/embedding inference. Local language-model hosting and horizontal scaling are outside this initial profile. Explicit supported local/hosted/none reranking retains its own resource and asset qualification. This does not claim that the proposed 25000-document/500000-vector expansion workload is supported.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

The first supported workload is intentionally small and concurrency is limited. Larger capacity remains an evidence-led expansion rather than a promise based on planning arithmetic.

Alice's old vectors, Bob's new build and a backup all count toward disk use. If another admission would cross the shared budget, it is rejected before effects instead of deleting retained data to make space.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-architecture/references/decision-supported-operating-envelope.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
