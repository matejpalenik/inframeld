# PD-INDEXING-03: Keep source passage identity stable when chunking changes

**Status:** PENDING

**Owner:** `inframeld-indexing`

**Issue kind:** Architecture and evidence contract.

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

Alice accepts an expected cancellation-policy passage from B1 using profile P1. Bob compares P2, which splits the same parsed text differently. The new chunks have different IDs, but a complete mapped passage should still count as covered. A genuinely different parse may instead be unscorable.

The metric correctly compares source spans rather than chunk IDs or fuzzy text. Canonical artifact identity, coordinate units, normalization and supported cross-profile mappings still need a concrete contract. If artifact identity is tied unnecessarily to chunk execution, ordinary chunking comparisons can become useless despite unchanged source content.

## Accepted context and evidence

DocumentVersion fixes source bytes. Processing generations record actual executions. A canonical parsed artifact describes the content from which chunks are selected. Coordinates identify where actual text came from and must match what downstream work used.

Preserve exact artifact/version identity, complete mapped coverage and explicit unscorable outcomes. Do not guess across incompatible parser output, fabricate coordinates or change denominators to hide unavailable evidence. Tables and discontiguous passages need explicit treatment.

## Alternatives and trade-offs

1. **Define canonical parsed content independently of chunk output.** Identify a qualified conversion artifact and map each chunk’s spans into it. This naturally supports different chunking over one parse, but requires deterministic identity/normalization rules and explicit transformed spans.
2. **Keep profile-specific artifacts with verified mapping.** Retain each artifact’s identity and qualify mappings only for supported transformations. This supports more conversion variation, but adds mapping machinery and more unscorable cases.

## Non-binding recommendation

**Proposal only.** Prefer a canonical conversion artifact independent of downstream chunk boundaries where the conversion is genuinely the same. Support only explicit proven transformations. Keep incompatible parses unscorable rather than inventing general cross-parser equivalence.

## Decision trigger and stopping boundary

Before defining parsed artifact identities, source-span fields, chunk transformation mappings or passage-coverage implementation.

Pause the coordinate/mapping contract. This does not reopen immutable source identity or permit fuzzy evaluation fallback.

## Architectural impact and dependencies

Knowledge provenance, Indexing conversion/chunking, generation payloads, Pipeline final-context attribution and Evaluation expected passages. Update source-to-chunk/evidence sequences and record definitions together.

Load neighboring decisions only under these conditions:

- [PD-EVALUATION-02: Coordinate fixed runs and expose honest protected results](../../inframeld-evaluation/references/decision-run-and-result-contracts.md). When designing metric/protected result representations.

## Open questions and required evidence

- Are offsets bytes, code points, tokens or another explicit unit?
- Are interval endpoints inclusive or exclusive?
- Which normalization occurs before coordinates are assigned?
- How are tables, merged and discontiguous spans represented?
- Which changed-chunking fixture must remain comparable and which parse change must be unscorable?

## Sources and finalization

- [Preparation and source coordinates](profiles-and-preparation.md).
- [Passage coverage](../../inframeld-evaluation/references/generation-and-review.md).
- [Processing and expected-passage records](records.md#indexing).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
