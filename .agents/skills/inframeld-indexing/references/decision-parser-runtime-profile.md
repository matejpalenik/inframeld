# PD-INDEXING-05: Select and prove a bounded parser runtime

**Status:** PENDING

**Owner:** `inframeld-indexing`

**Issue kind:** Implementation profile and security qualification.

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

Alice uploads a supported PDF that expands into enormous text or leaves child processes running. Bob uploads another document immediately afterward. The parser must fail within its limits, remove the whole attempt and keep Bob’s attempt isolated.

The no-network/no-secret sandbox and accepted upload limit are selected. Numeric page/text/chunk/token/time/scratch limits and the exact supported image, policies and host combination remain unqualified. File-size bounds alone cannot prevent host exhaustion.

## Accepted context and evidence

Preserve the 25 MiB upload bound, offline pinned processing assets, no privileged fallback, closed inherited descriptors, validated output and complete process-tree teardown. Domain and application state stay outside the restricted child.

The supported host, kernel controls, bubblewrap/seccomp/LSM policy and image must be tested together. A configuration file or container flag alone does not prove isolation. Reranker behavior and remote gateway calls retain their separate boundaries.

## Alternatives and trade-offs

1. **Start with one narrow tested host/profile.** Choose conservative numerical ceilings and qualify the complete supported combination. This reduces support variation, but rejects larger legitimate inputs until measured expansion.
2. **Offer a small set of explicitly qualified profiles.** Each profile has documented limits and passes the same hostile tests. This helps varied workloads, but multiplies release evidence and operator configuration.

## Non-binding recommendation

**Proposal only.** Prefer one conservative profile first. Measure supported ordinary PDFs and adversarial fixtures before choosing numerical values. Increase limits only with evidence, without weakening the accepted isolation boundary.

## Decision trigger and stopping boundary

Before fixing parser numerical limits or shipping the assembled parser image/sandbox/host profile.

Unselected numerical/profile interfaces need discussion. Qualification remains a release gate and must not prevent authorized hostile-fixture testing.

## Architectural impact and dependencies

Indexing preparation/supervisor, Knowledge admission failure reporting, deployment readiness and worker resource budgets. Update restricted-parser runtime/teardown sequences when the supported mechanism is selected.

Load neighboring decisions only under these conditions:

- [PD-ARCHITECTURE-01: Select a measured supported workload and resource envelope](../../inframeld-architecture/references/decision-supported-operating-envelope.md). For whole-host and concurrent workload bounds.

## Open questions and required evidence

- What limits bound expanded content and total scratch usage?
- Which exact host and policies are supported?
- How are all descendants stopped after timeout/restart?
- Which self-test rejects unsupported isolation?
- Can the same profile process the normal fixture set within measured resource budgets?

## Sources and finalization

- [Sandbox and qualification](../../../../docs/development/ingestion-security.md).
- [Restricted execution decision](../../../../docs/adr/ADR-0034-process-untrusted-documents-inside-a-restricted-execution-boundary.md).
- [Processing profile records](../../../../docs/development/data-model.md#indexing).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
