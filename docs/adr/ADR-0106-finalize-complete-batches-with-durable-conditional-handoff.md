# ADR-0106: Finalize complete batches with durable conditional handoff

**Status:** Accepted

**Date:** 2026-10-29. The developer explicitly approved all three document-batch, prepared-binding and source-coordinate proposals, including their detailed contracts, and requested repository and GitHub recording. Acceptance selects logical behavior, not implemented code or passing qualification.

## Context and Problem Statement

Alice loses a batch response while Bob changes the collection selection. Successful document admissions must remain recoverable without publishing an incomplete or silently changed corpus.

## Considered Options

- Durable per-document admissions followed by conditional complete-selection finalization and a durable handoff. Selected.
- One transaction over all admission metadata, requiring bounded already durable inputs and suitable lower-level transaction composition.

## Decision Outcome

Preserve original parent/child identities and fixed inputs. Admit each complete durable source independently. Finalize only the exact complete selection under current authority and the expected base revision. Commit selection, completion, safe outcome, audit and durable continuation together in a short application-owned transaction. A competing selection conflicts without losing admitted versions or silently merging. Downstream Build and target-specific publication retain separate authority.

The [approved PD-KNOWLEDGE-01 contract](../../.agents/skills/inframeld-knowledge/references/decision-complete-batch-handoff.md#approved-resolution) owns the complete behavior, examples and required cases.

## Consequences

Recovery needs durable parent/child progress and deliberate conflict handling. Successful input is not lost, and partial batches cannot silently become complete. Large membership inventories are prepared in bounded pages. No new workflow engine or all-Deployment transaction is introduced.

Backend implementation, public schemas and runtime qualification remain separate delivery work.

## Links

- [Stable decision reference](../../.agents/skills/inframeld-knowledge/references/decision-complete-batch-handoff.md)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
