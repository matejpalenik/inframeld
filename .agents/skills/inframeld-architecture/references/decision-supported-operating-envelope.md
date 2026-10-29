# PD-ARCHITECTURE-01: Select a measured supported workload and resource envelope

**Status:** ACCEPTED on 2026-10-29 in [ADR-0121](../../../../docs/adr/ADR-0121-qualify-a-small-single-host-operating-envelope.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-architecture`

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Contents

- [Approved resolution](#approved-resolution)
- [Why and example](#why-and-example)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Historical context and alternatives](#historical-context-and-alternatives)
- [Sources and finalization](#sources-and-finalization)

<a id="non-binding-recommendation"></a>

## Approved resolution

Select the existing 16-vCPU/64 GiB RAM/1 TB usable SSD or NVMe single-host Docker Compose installation as the first qualification target, with remote generation/embedding inference. Local language-model hosting and horizontal scaling are outside this initial profile. Explicit supported local/hosted/none reranking retains its own resource and asset qualification. This does not claim that the proposed 25000-document/500000-vector expansion workload is supported.

Initial installation-wide ceilings are 200current documents,2000current chunks and 10000physical vectors including retained/pending generations. Allow up to two prepared embedding profiles for isolated migration, each with at most 1536 dimensions. Use two fixed shards per index and at most four physical shards across those profiles. Bound selected generation IDs to 1000and serialized server filters to 64 KiB per shard. A dimension/filter bound rejects unsupported work without truncating vectors, splitting unbounded queries, widening access or changing profiles/models.

Allow one active answer execution, one active application-worker attempt and the existing separate recovery attempt. Reserve at most eight ordinary admitted jobs total, queued plus running. Ordinary job work has a two-hour deadline including automatic retries, with at most 24 hours queued waiting before its explicit terminal/unfinished outcome. Answer execution after preparation has 180 seconds total; each provider call has at most 120 seconds or its remaining operation time, whichever is smaller. Preserve the existing three application attempts and recovery-specific exception. These limits do not authorize retry of uncertain paid work or erase unfinished cleanup obligations when an attempt expires.

Reserve foreseeable document/chunk/vector/spool/queue and required result growth atomically before admission. Count retained, pending and pinned data in the applicable physical/storage budgets. Cap protected live state at 100 GiB and keep a separate full backup staging allocation. Stop unsafe new growth before free disk drops below 20 percent of usable capacity, including temporary/spool/backup coexistence. The agreed parser, history, safety-metadata and spool sub-budgets are part of this total, not independent extra host capacity. Low storage keeps restrictions/recovery evidence and existing obligations; it is not permission to evict pinned content or bypass authorization. Return bounded explicit overloaded/capacity/unavailable outcomes with existing retry semantics.

Run bounded read-only health auditing independently of the nonpreemptive ordinary job slot. The single vector writer and existing recovery process remain separate responsibilities, not a new pool per capability. Operator signals include queue depth/oldest age, active limits, disk/spool/history reservations, audit age/health, unresolved paid/storage calls and cleanup delay, without exposing protected product content.

Chosen qualification objectives are retrieval/authorization/filter p 95 at most 1second at one active query during a small build; scoped recall@10 at least 0.95against an exact permitted-scope baseline; and at most two minutes of one-document platform overhead. Report sample sizes, failures and queueing; measure provider/parser time separately. Select no end-to-end throughput or fixed first-answer promise. Preserve the accepted flexible first-answer goal. Tests must demonstrate mixed-load memory/disk/deadline/saturation behavior before any support claim. If a target fails, leave it unqualified and fix/restrict the affected implementation; do not silently enlarge ceilings, weaken checks or advertise unmeasured capacity.

## Why and example

Several individually bounded jobs can still exhaust one shared host. One conservative whole-installation profile gives every owner the same budget.

Alice's old vectors, Bob's new build and a backup all count toward disk use. If another admission would cross the shared budget, it is rejected before effects instead of deleting retained data to make space.

The first supported workload is intentionally small and concurrency is limited. Larger capacity remains an evidence-led expansion rather than a promise based on planning arithmetic.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Chosen host/artifact manifest, mixed query/build/audit/backup load, filter recall and p 95 samples, every quota and deadline, low storage, queued saturation, recovery isolation and preserved safety obligations.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Deployment profile, every domain’s admission/batching, worker/gateway limits, cleanup headroom and operator visibility. Module/runtime diagrams must continue showing one host rather than implied independent capacity zones.

Load neighboring decisions only under these conditions:

- [PD-INDEXING-05 (accepted): Select and prove a bounded parser runtime](../../inframeld-indexing/references/decision-parser-runtime-profile.md). For parser resource limits.
- [PD-CONTRACTS-05 (accepted): Qualify cleanup and recovery under a full bounded queue](../../inframeld-application-contracts/references/decision-queue-saturation-and-cleanup.md). For mixed-load queue behavior.
- [PD-KNOWLEDGE-02 (accepted): Choose bounded retention without weakening explicit erasure](../../inframeld-knowledge/references/decision-retention-erasure-policy.md). For bounded retained history.
- [PD-ARCHITECTURE-02 (accepted): Match availability and recovery claims to the supported deployment](decision-availability-backup-and-restore.md). For backup resource and availability costs.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Alice ingests a handbook while Production handles questions and Bob runs an evaluation. Full membership verification, permitted-document filters, parser scratch files and model holds share one host. Each operation may be individually bounded while their combined disk or memory use is unsafe.

The design requires bounded work and overload handling, but its numerical workload, resource ceilings and latency/concurrency claims are unmeasured. The proposed 25,000 documents and roughly 500,000 vectors are qualification inputs, not a capacity promise.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Preserve single-server Docker Compose, remote model inference where assumed, one modular backend and the supported singleton vector writer. Membership/filter work can grow with documents, and complete readiness verification can inspect the selected inventory. Do not hide those costs behind a “ready” flag.

Admission must stop before queue/storage/work budgets are exhausted. The smaller 100–200-document trial is a proposed starting qualification too, not evidence. A million-document or horizontally elastic claim is outside the established envelope.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Qualify a conservative small initial profile.** Measure one supported host with explicit limits for queues, parsing, filters, manifests, retained payloads and histories. This lowers initial capacity claims but gives clear reproducible support.
2. **Qualify the larger proposed workload before release.** Test the 25k-document planning workload with controlled concurrency and retention. This may serve more users initially, but costs more qualification time and may require reducing the supported profile if it fails.

## Sources and finalization

- [Deployment qualification](runtime-deployment-and-storage.md).
- [Indexing capacity calculations](../../inframeld-indexing/references/profiles-and-preparation.md).
- [Delivery evidence](../../../../docs/development/definition-of-done.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
