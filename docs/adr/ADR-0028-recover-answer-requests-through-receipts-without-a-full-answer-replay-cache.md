# ADR-0028: Recover answer requests through receipts without a full-answer replay cache

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Keeping every answer for idempotency replay would create another sensitive content archive. Regenerating an answer after a lost response could also repeat model costs and produce different content.

## Considered Options

- Return safe receipt status for a previously completed answer request.
- Retain full answers indefinitely for replay.
- Regenerate the answer automatically when its response was lost.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use the answer receipt to recover the recorded outcome of a completed query without a hidden full-answer replay cache or automatic regeneration. Record the required serving and evidence provenance, protect receipt reads with current access, and retain the documented distinction between the original result and replay. Fixed integrations retain their own successful answer when needed.

**Example.** The first request generated an answer but the connection dropped. Retrying returns the recorded receipt outcome; it does not quietly call the model again.

## Consequences

- Recovery explains what happened without creating a second permanent production-answer store.
- A caller that lost the original answer may recover its receipt rather than its text. Receipt retention, evidence availability, and current authorization limit later inspection.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current jobs and idempotency](../development/jobs-and-idempotency.md).
- [Current answer feedback](../development/answer-feedback.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0026](ADR-0026-persist-background-work-through-controlled-durable-attempts.md), [ADR-0027](ADR-0027-identify-repeated-requests-by-caller-and-request-meaning.md), [ADR-0029](ADR-0029-use-expected-revisions-to-protect-competing-changes.md).
