# PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure

**Status:** PENDING

**Owner:** `inframeld-knowledge`

**Issue kind:** Cross-domain lifecycle contract.

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

Alice retains an old benchmark based on handbook B1. Bob erases that handbook. A live release may also share some derived artifacts. Keeping an immutable benchmark identity cannot justify retaining erased question text, while deleting shared vectors indiscriminately can break unrelated permitted work.

Current guides define pins, historical unavailability and erasure precedence. Some record families still need exact retention periods and storage bounds. Already selected values stay fixed, including configurable 30-day workload-trace retention and the existing completed synchronous idempotency expiry. This discussion fills unselected policy details rather than resetting every family’s defaults. Without them, history, jobs, receipts, diagnostic data and derived artifacts can accumulate indefinitely or expire inconsistently.

## Accepted context and evidence

Knowledge owns source lifecycle and erasure. Each neighboring owner retains its records and protected-read policy. Pins protect needed artifacts from ordinary cleanup, not explicit erasure. Source-derived cases, reference answers, judgments and traces can disclose the source and must participate in erasure.

An immutable record keeps its identity, not permanent content availability. Do not use receipts or operation metadata as a full-answer archive. Retained snapshots do not authorize automatic reconstruction or paid re-embedding. Trace opt-out and explicit Evaluation retention remain different controls.

## Alternatives and trade-offs

1. **Publish a small bounded installation retention profile.** Select documented finite defaults and operator bounds for each record family, with existing live-reference exceptions. This is predictable and easier to operate, but may be less flexible for varied customers.
2. **Use family-specific policies within common operator bounds.** Let owning workflows expose only their agreed settings while sharing erasure/reference rules. This fits differing evidence lifetimes, but requires more policy validation and clear precedence.

## Non-binding recommendation

**Proposal only.** Prefer a small finite profile first, with per-family rules where required by existing behavior. Define which minimal non-content markers survive erasure. Choose actual periods from workload and support needs rather than inventing universal durations during documentation authoring.

## Decision trigger and stopping boundary

Before implementing retention configuration, bounded history storage, expiry or cross-domain source-erasure cleanup.

Pause choices of periods, limits and derived-content cleanup contracts. The already accepted rule to block erased content is not pending.

## Architectural impact and dependencies

Knowledge source deletion, Indexing references, Pipeline history/receipts/feedback, Evaluation evidence, traces, jobs and backups. Owning guides still specify their records. Update erasure/retention sequences where actual effects change.

Load neighboring decisions only under these conditions:

- [PD-ARCHITECTURE-01: Select a measured supported workload and resource envelope](../../inframeld-architecture/references/decision-supported-operating-envelope.md). For disk/headroom and history budgets.
- [PD-INDEXING-04: Qualify frozen storage retries and final erasure barriers](../../inframeld-indexing/references/decision-storage-retries-and-erasure.md). For the physical completion barrier.
- [PD-ARCHITECTURE-02: Match availability and recovery claims to the supported deployment](../../inframeld-architecture/references/decision-availability-backup-and-restore.md). For backup retention and restoration restrictions.

## Open questions and required evidence

The deletion-status viewer subquestion was explicitly resolved on 2026-10-25 by [ADR-0080](../../../../docs/adr/ADR-0080-limit-product-deletion-status-to-the-initiating-human.md). Product status is initiator-only under current eligibility and the original operation binding. Administrator status alone is insufficient. This entry remains **PENDING** for the other questions below, including retention and exact delivery contracts.

- What finite default and maximum apply to each record family?
- Which live/rollback references prevent routine expiry?
- Which non-content identity/audit markers may remain after erasure?
- How do failed cleanup, concurrent imports and late writes retain obligations?
- How are expired backup copies and off-host restrictions handled under the existing recovery baseline?

## Sources and finalization

- [Retention and explicit erasure](deletion-and-retention.md).
- [Protected Evaluation history](../../inframeld-evaluation/references/history-and-dataset-transfer.md#history).
- [Pipeline and supporting records](../../inframeld-application-contracts/references/components-and-services.md#shared-supporting-records).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
