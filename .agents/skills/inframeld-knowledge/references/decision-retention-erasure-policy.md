# PD-KNOWLEDGE-02: Choose bounded retention without weakening explicit erasure

**Status:** ACCEPTED on 2026-10-29 in [ADR-0117](../../../../docs/adr/ADR-0117-bound-retention-while-preserving-erasure-and-safety-obligations.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-knowledge`

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

Use one finite installation retention profile with owner-specific content rules. Select these default/operator-maximum periods: unreferenced source versions, collection revisions and derived artifacts 30/90 days; historical working configuration 90/365 days; completed execution-capture metadata 7/30 days; Evaluation run answers, judgments and supporting evidence 90/365 days; answer receipts, associated feedback and deletion-status projections 30/90 days; completed job/attempt history 30/90 days; protected workload traces 30/90 days; content-free operational logs 7/30 days; ordinary audit history 365/730 days. These are selected policy values, not regulatory advice or measured cleanup performance. Project workload-trace retention keeps its already accepted configurable 30-day default. A shorter setting needs a reviewed ordinary authorized policy update, not a hidden global reset.

Current authoritative resources, current/candidate/previous Deployment dependencies, retained approved benchmark/case references and active operations keep required references. Age alone cannot evict them. Unreferenced content becomes eligible for bounded expiry; explicit erasure overrides ordinary references. Immutable records preserve identity, not permanent content availability. Keep current access/audience/source checks on every history read and mark expired/erased evidence unavailable rather than rebuilding it or paying for fresh embeddings.

Keep existing completed synchronous-idempotency deadlines, its at-least 24-hour floor and active-work retention. Publish original expiry and never extend it on reads/replay. Delete transient ordinary query input/output when execution ends unless separately authorized Evaluation/diagnostic storage owns that content. Missing required original input makes continuation ineligible. Do not create a receipt/operation full-answer archive.

Select a 10 GiB installation retained-history/evidence budget, operator-configurable up to 20 GiB within the whole-host ceiling. Reserve foreseeable mandatory receipt/history space before business admission. At capacity reject new mandatory-persistence work before effects; optional diagnostic capture may drop with its existing partial/unavailable meaning. Do not shorten promised retention silently to create room. Operators may deliberately lower a policy within the existing authority/review rules and accept ordinary expiry consequences.

Permanent retired physical/resource identities, unresolved paid holds, unfinished erasure/recovery obligations and restriction evidence needed by retained backups do not expire under these TTLs. Reserve 1 GiB for minimal safety metadata and 256 MiB emergency headroom for restrictions/cleanup evidence. Exhaustion stops ordinary admission instead of deleting safety facts. If emergency restriction persistence cannot be guaranteed, fail closed for affected product access and use the existing protected host recovery procedure. Keep non-reusable attribution IDs and only necessary non-content actor/time/reason/effect records; remove unnecessary direct personal attributes.

Erasure first invalidates affected access, dispatch and protected derived-content reads, then retains a durable original cleanup obligation over exact artifacts and shared-generation ownership. Remove source-derived questions, reference answers, judgments, traces and caches where required without deleting unrelated shared authorized data. Imports/late writes use the same tombstones/generations and cannot recreate erased history. Keep initiator-only deletion-status authority from ADR-0080. The initial live-cleanup objective is 24 hours, not a completion claim. Physical completion follows the qualified storage barrier; missed objectives leave access blocked and cleanup pending. Backups and copies already exported have their separately disclosed limits.

## Why and example

Keeping everything forever eventually exhausts the host and makes erasure harder. Finite defaults make normal growth predictable, while safety obligations cannot be discarded just because a timer expired.

Alice's old evaluation evidence normally expires after 90 days. If Bob erases its source sooner, protected derived text becomes unavailable immediately. A still-unresolved cleanup record survives until its obligation and backup restrictions are safely satisfied.

Historical experiments may become unavailable. Live references and required safety evidence remain, so reaching storage limits stops new work rather than destroying needed records.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Each record-family expiry/default/max, live references, current source protection, derived erasure, shared data, quota reservation, emergency headroom, late writes/imports and backup restriction retention.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Knowledge source deletion, Indexing references, Pipeline history/receipts/feedback, Evaluation evidence, traces, jobs and backups. Owning guides still specify their records. Update erasure/retention sequences where actual effects change.

Load neighboring decisions only under these conditions:

- [PD-ARCHITECTURE-01 (accepted): Select a measured supported workload and resource envelope](../../inframeld-architecture/references/decision-supported-operating-envelope.md). For disk/headroom and history budgets.
- [PD-INDEXING-04 (accepted): Qualify frozen storage retries and final erasure barriers](../../inframeld-indexing/references/decision-storage-retries-and-erasure.md). For the physical completion barrier.
- [PD-ARCHITECTURE-02 (accepted): Match availability and recovery claims to the supported deployment](../../inframeld-architecture/references/decision-availability-backup-and-restore.md). For backup retention and restoration restrictions.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Alice retains an old benchmark based on handbook B1. Bob erases that handbook. A live release may also share some derived artifacts. Keeping an immutable benchmark identity cannot justify retaining erased question text, while deleting shared vectors indiscriminately can break unrelated permitted work.

Current guides define pins, historical unavailability and erasure precedence. Some record families still need exact retention periods and storage bounds. Already selected values stay fixed, including configurable 30-day workload-trace retention and the existing completed synchronous idempotency expiry. This discussion fills unselected policy details rather than resetting every family’s defaults. Without them, history, jobs, receipts, diagnostic data and derived artifacts can accumulate indefinitely or expire inconsistently.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

Knowledge owns source lifecycle and erasure. Each neighboring owner retains its records and protected-read policy. Pins protect needed artifacts from ordinary cleanup, not explicit erasure. Source-derived cases, reference answers, judgments and traces can disclose the source and must participate in erasure.

An immutable record keeps its identity, not permanent content availability. Do not use receipts or operation metadata as a full-answer archive. Retained snapshots do not authorize automatic reconstruction or paid re-embedding. Trace opt-out and explicit Evaluation retention remain different controls.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Publish a small bounded installation retention profile.** Select documented finite defaults and operator bounds for each record family, with existing live-reference exceptions. This is predictable and easier to operate, but may be less flexible for varied customers.
2. **Use family-specific policies within common operator bounds.** Let owning workflows expose only their agreed settings while sharing erasure/reference rules. This fits differing evidence lifetimes, but requires more policy validation and clear precedence.

## Sources and finalization

- [Retention and explicit erasure](deletion-and-retention.md).
- [Protected Evaluation history](../../inframeld-evaluation/references/history-and-dataset-transfer.md#history).
- [Pipeline and supporting records](../../inframeld-application-contracts/references/components-and-services.md#shared-supporting-records).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
