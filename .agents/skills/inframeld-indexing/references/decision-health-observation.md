# PD-INDEXING-02: Define what current index health can actually detect

**Status:** PENDING

**Owner:** `inframeld-indexing`

**Issue kind:** Architecture and observation contract.

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

One published Chroma record disappears while its shard still answers searches. Alice asks a question whose nearest results never include that missing record. Validating returned results succeeds, and an unchanged SQL health revision cannot reveal an omission that nobody has observed.

Readiness verification and invalidation of known unhealthy dependencies are accepted. Normal-operation detection triggers, observation scope, freshness and unknown-health outcomes are not selected. The design does not promise instant detection of every silent external loss.

## Accepted context and evidence

Build verification checks expected inventory and selected bytes. Queries validate returned identities/content references and compare dependency-health generations at the documented boundaries. Restore verifies dependencies privately. Reconciliation belongs to Indexing.

A health generation is a revision that changes when a known condition changes. It is not a sensor. A successful health observation establishes only its checked scope. Already-sent content cannot be recalled, and no observation makes remote state atomic with PostgreSQL.

## Alternatives and trade-offs

1. **Bounded periodic plus event-triggered audits.** Check defined inventories/integrity on a schedule and after failures or lifecycle events. This offers an explicit detection window at controlled cost, but silent loss may persist between observations.
2. **Broader use-time verification.** Verify more of a selected dependency before using it. This narrows some detection gaps, but can make normal queries expensive and still needs a precise scope rather than a universal health claim.
3. **Demand-triggered checks with an explicit limited guarantee.** Rely on build, restore, observed failures and returned-result validation, clearly disclosing what is not continuously detected. This is simpler, but supports weaker ongoing integrity assurances.

## Non-binding recommendation

**Proposal only.** Prefer bounded event-triggered and periodic verification if the measured workload can support it. Decide freshness and unknown-state behavior explicitly. Do not imply a full-corpus scan per query or instant silent-loss detection.

## Decision trigger and stopping boundary

Before implementing reconciliation, ongoing serving-health checks or claims about how quickly storage loss is detected.

Pause the affected health/detection contract. Accepted build verification and known-loss invalidation are not optional pending policy.

## Architectural impact and dependencies

Indexing health projection/reconciler, Pipeline pre-send/disclosure checks, Releases usability, operational readiness and restore. Update health-observation and invalidation sequences.

Load neighboring decisions only under these conditions:

- [PD-ARCHITECTURE-01: Select a measured supported workload and resource envelope](../../inframeld-architecture/references/decision-supported-operating-envelope.md). For verification cost and acceptable operating bounds.

## Open questions and required evidence

- What failure classes must v1 detect, and within what tested window?
- What inventory/bytes does each observation cover?
- Who advances the health revision and how is recovery reverified?
- What does admission/use do when health is stale or unknown?

## Sources and finalization

- [Health and retention protocol](retirement-and-erasure.md#retirement).
- [Remaining health contract](architecture.md#indexing-capability-boundaries).
- [Materialization records](records.md#indexing).
- [Restoration checks](../../../../docs/development/operations/upgrades.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
