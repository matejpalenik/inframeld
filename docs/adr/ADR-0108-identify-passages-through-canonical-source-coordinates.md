# ADR-0108: Identify passages through canonical source coordinates

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three document-batch, prepared-binding and source-coordinate proposals, including their detailed contracts, and requested repository and GitHub recording. Acceptance selects logical behavior, not implemented code or passing qualification.

## Context and Problem Statement

Different chunking over the same parsed document changes chunk IDs. Evaluation needs exact source identity and coordinates to distinguish complete coverage, an ordinary miss and an unsupported comparison.

## Considered Options

- Canonical conversion artifacts independent of chunk boundaries with explicit source mappings. Selected.
- Profile-specific artifacts plus broader cross-parser mapping, increasing conversion and qualification complexity.

## Decision Outcome

Define canonical application-owned conversion identity before chunking, including exact format/recipe/content identity while excluding chunk-only settings. Normalize line endings to LF, otherwise preserve Unicode, case and whitespace. Use zero-based Unicode code-point half-open ranges and explicit segment mappings for actual returned text. Comparable union coverage determines Found or Not found. Missing or unproven coordinate correspondence is Unscorable, with honest protected populations.

The [approved PD-INDEXING-03 contract](../../.agents/skills/inframeld-indexing/references/decision-source-coordinates.md#approved-resolution) owns the complete behavior, examples and required cases.

## Consequences

Chunk-size experiments remain comparable while canonical artifacts and mappings require storage and qualification. Changed parser/OCR output is not presumed equivalent. No universal fuzzy mapping engine or changed context-assembly behavior is introduced.

Backend implementation, public schemas and runtime qualification remain separate delivery work.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-indexing/references/decision-source-coordinates.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
