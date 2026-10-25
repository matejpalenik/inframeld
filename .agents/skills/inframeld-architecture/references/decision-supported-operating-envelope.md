# PD-ARCHITECTURE-01: Select a measured supported workload and resource envelope

**Status:** PENDING

**Owner:** `inframeld-architecture`

**Issue kind:** Operating profile and capacity qualification.

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

Alice ingests a handbook while Production handles questions and Bob runs an evaluation. Full membership verification, permitted-document filters, parser scratch files and model holds share one host. Each operation may be individually bounded while their combined disk or memory use is unsafe.

The design requires bounded work and overload handling, but its numerical workload, resource ceilings and latency/concurrency claims are unmeasured. The proposed 25,000 documents and roughly 500,000 vectors are qualification inputs, not a capacity promise.

## Accepted context and evidence

Preserve single-server Docker Compose, remote model inference where assumed, one modular backend and the supported singleton vector writer. Membership/filter work can grow with documents, and complete readiness verification can inspect the selected inventory. Do not hide those costs behind a “ready” flag.

Admission must stop before queue/storage/work budgets are exhausted. The smaller 100–200-document trial is a proposed starting qualification too, not evidence. A million-document or horizontally elastic claim is outside the established envelope.

## Alternatives and trade-offs

1. **Qualify a conservative small initial profile.** Measure one supported host with explicit limits for queues, parsing, filters, manifests, retained payloads and histories. This lowers initial capacity claims but gives clear reproducible support.
2. **Qualify the larger proposed workload before release.** Test the 25k-document planning workload with controlled concurrency and retention. This may serve more users initially, but costs more qualification time and may require reducing the supported profile if it fails.

## Non-binding recommendation

**Proposal only.** Prefer a small measured initial profile, then expand only after mixed-load tests pass. Choose actual ceilings and performance objectives from measurements. Do not add infrastructure simply to preserve an unmeasured planning number.

## Decision trigger and stopping boundary

Before fixing production resource/admission limits or advertising supported corpus size, throughput, latency or concurrency.

Unselected limits need approval before dependent enforcement contracts are fixed. Capacity evidence gates claims, not the tests that establish it.

## Architectural impact and dependencies

Deployment profile, every domain’s admission/batching, worker/gateway limits, cleanup headroom and operator visibility. Module/runtime diagrams must continue showing one host rather than implied independent capacity zones.

Load neighboring decisions only under these conditions:

- [PD-INDEXING-05: Select and prove a bounded parser runtime](../../inframeld-indexing/references/decision-parser-runtime-profile.md). For parser resource limits.
- [PD-CONTRACTS-05: Qualify cleanup and recovery under a full bounded queue](../../inframeld-application-contracts/references/decision-queue-saturation-and-cleanup.md). For mixed-load queue behavior.
- [PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure](../../inframeld-knowledge/references/decision-retention-erasure-policy.md). For bounded retained history.
- [PD-ARCHITECTURE-02: Match availability and recovery claims to the supported deployment](decision-availability-backup-and-restore.md). For backup resource and availability costs.

## Open questions and required evidence

- Which hardware, model locality and retained history are in the supported profile?
- What p95/throughput/concurrency objectives matter for the first users?
- What combined memory/disk/spool/filter/queue limits prevent exhaustion?
- Which exact saturation outcome and recovery path does each admission expose?

## Sources and finalization

- [Deployment qualification](../../../../docs/development/deployment.md).
- [Indexing capacity calculations](../../../../docs/development/indexing.md).
- [Delivery evidence](../../../../docs/development/definition-of-done.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
