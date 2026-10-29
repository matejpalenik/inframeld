# PD-INDEXING-03: Keep source passage identity stable when chunking changes

**Status:** ACCEPTED

**Approval date:** 2026-10-29

**Owner:** `inframeld-indexing`

**Issue kind:** Architecture and evidence contract.

The developer explicitly approved this proposal and its detailed batch-3 contract on 2026-10-29, then requested repository and GitHub recording. [ADR-0108](../../../../docs/adr/ADR-0108-identify-passages-through-canonical-source-coordinates.md) records the decision. Acceptance selects logical behavior, not implemented code or passing qualification.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Approved resolution](#approved-resolution)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice accepts an expected cancellation-policy passage from B1 using profile P1. Bob compares P2, which splits the same parsed text differently. The new chunks have different IDs, but a complete mapped passage should still count as covered. A genuinely different parse may instead be unscorable.

The metric correctly compares source spans rather than chunk IDs or fuzzy text. Canonical artifact identity, coordinate units, normalization and supported cross-profile mappings are selected by the approved resolution below. If artifact identity is tied unnecessarily to chunk execution, ordinary chunking comparisons can become useless despite unchanged source content.

## Accepted context and evidence

DocumentVersion fixes source bytes. Processing generations record actual executions. A canonical parsed artifact describes the content from which chunks are selected. Coordinates identify where actual text came from and must match what downstream work used.

Preserve exact artifact/version identity, complete mapped coverage and explicit unscorable outcomes. Do not guess across incompatible parser output, fabricate coordinates or change denominators to hide unavailable evidence. Tables and discontiguous passages need explicit treatment.

## Alternatives and trade-offs

1. **Define canonical parsed content independently of chunk output.** Identify a qualified conversion artifact and map each chunk’s spans into it. This naturally supports different chunking over one parse, but requires deterministic identity/normalization rules and explicit transformed spans.
2. **Keep profile-specific artifacts with verified mapping.** Retain each artifact’s identity and qualify mappings only for supported transformations. This supports more conversion variation, but adds mapping machinery and more unscorable cases.

<a id="non-binding-recommendation"></a>

## Approved resolution

Use an immutable application-owned canonical conversion artifact before chunking. Its identity binds the organization/Project, DocumentVersion, canonical format/version, supported converter implementation/assets and conversion settings, plus the exact canonical content/structure digest. Exclude chunk-only settings, chunk IDs and execution timestamps from conversion identity. Separate ProcessingGenerations remain distinct. They may reference the same genuinely identical canonical artifact. A changed converter recipe or different canonical output does not become equivalent just because source bytes match.

For the initial coordinate format, preserve structured block/table provenance and define one deterministic canonical text stream. Normalize line endings to LF before assigning coordinates. Preserve the converter's Unicode code-point sequence, case and whitespace otherwise. No implicit Unicode composition, case folding, whitespace collapse or post-coordinate cleanup. Persist/hash the exact canonical representation. Versioned serialization uses document reading order, LF between text blocks, TAB between table cells and LF between table rows. Separators are structural boundaries, not evidence of additional source words. Qualified conversion fixtures must cover embedded delimiters, empty cells and multiline cell text while preserving cell identities in the structured artifact.

Use zero-based Unicode code-point offsets and half-open ranges [start,end): include the start, exclude the end. These offsets are not UTF-8 byte counts, UTF-16 code units, model tokens or visual glyph counts. Reject invalid, out-of-bounds or reversed ranges, and validate boundaries against the stored artifact. Adapters explicitly translate their own indexing units. A combining sequence can contain several code points. Do not split a user-selected grapheme when the supported selection boundary can preserve it.

Each source span includes exact DocumentVersion/artifact identity and a range in that artifact. A returned or transformed chunk carries an ordered mapping from its actual text segments to one or more source spans. Discontiguous excerpts are separate spans, never the broad start/end envelope that would falsely include missing text. Repeated table headers may map to the actual original header span. Generated labels, summaries or other synthetic text receive no invented source span. Changing header behavior before conversion creates a different conversion artifact, while mapped chunk-only repetition need not.

An expected passage freezes its source spans and reconstructible protected evidence. At each named stage, Evaluation calculates the union of actual comparable returned spans. Larger chunks or several adjacent chunks can establish full coverage. Overlap and duplicated headers count once. Valid comparable partial coverage is Not found. An unavailable expected artifact or unsupported mapping is Unscorable with its reason. Preserve admitted/scored/unscorable/excluded counts under current disclosure rules. Do not hide a mapping failure by silently shrinking the reported population, or treat it as a proven retrieval miss.

Initial support compares the same canonical artifact and explicitly verified exact segment mappings. Changed parser/OCR output remains unscorable across artifacts unless a separately qualified supported mapping proves the required exact correspondence. No fuzzy text lookup, semantic guess or universal cross-parser mapper is implied. Final-context attribution covers only text actually retained. This decision does not change the accepted whole-passage context assembly rule.

## Alice and Bob example

Alice's expected passage covers [100,180) in artifact X. Bob's new chunker returns [80,140) and [140,200) from X. Their union covers the expectation, so it is Found despite new chunk IDs. If his returned text ends at 150, it is Not found. If a new OCR output changes artifact X into Y without a qualified mapping, it is Unscorable. In the text A🙂B, the emoji occupies [1,2) under the selected code-point convention.

## Decision trigger and stopping boundary

Apply this accepted contract when the original trigger matches. Concrete method names and physical schemas remain ordinary implementation choices under the repository conventions. Do not reopen the approved policy. Separately pending neighboring choices retain their own triggers. Qualification gaps limit release claims, not authorized evidence gathering.

## Architectural impact and dependencies

Knowledge provenance, Indexing conversion/chunking, generation payloads, Pipeline final-context attribution and Evaluation expected passages. Update source-to-chunk/evidence sequences and record definitions together.

Load neighboring decisions only under these conditions:

- [PD-EVALUATION-02 (accepted): Coordinate fixed runs and expose honest protected results](../../inframeld-evaluation/references/decision-run-and-result-contracts.md). When designing metric/protected result representations.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

These are required cases and evidence, not passing tests.

Identical conversion with different chunk sizes, repeated sentences, adjacent/discontiguous/overlapping spans, combining characters and emoji, LF normalization, structured tables and repeated headers, transformed text, final-context omissions, changed OCR/parser output, unavailable artifacts and source erasure. Demonstrate complete coverage and explicit honest unscorable populations without extra parsing/model calls merely to score the starter metric.

## Sources and finalization

- [W3C Text Position Selector](https://www.w3.org/TR/annotation-model/#text-position-selector) is precedent for the offset convention. It does not require JSON-LD or select Inframeld's canonical serialization.

- [Preparation and source coordinates](profiles-and-preparation.md).
- [Passage coverage](../../inframeld-evaluation/references/generation-and-review.md).
- [Processing and expected-passage records](records.md#indexing).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application edits, a paid qualification call or claims of successful runtime qualification.
