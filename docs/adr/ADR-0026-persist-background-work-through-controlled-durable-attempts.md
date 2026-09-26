# ADR-0026: Persist background work through controlled durable attempts

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Uploads, builds, and evaluations can outlive a browser session or worker process. Failures must not make unfinished work disappear or let an old attempt publish after a replacement took ownership.

## Considered Options

- Persist jobs and attempt ownership in PostgreSQL through short transactions.
- Keep long-running work only in a request process.
- Introduce a general workflow engine or treat every external timeout as an automatic retry.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Record admitted work durably and execute it through controlled attempts. Use current ownership and fencing checks before publishing state. Keep external calls outside short SQL transactions and distinguish known failure from an uncertain external outcome. Supporting job records remain part of the application, not another business domain.

**Example.** A replacement worker can take over a job, but the earlier worker cannot publish simply because its delayed external response finally arrives.

## Consequences

- Work can continue or be examined after disconnection or restart, with explicit ownership of state publication.
- A lease or database fence cannot cancel a request already sent to another system. Recovery must preserve uncertainty and must not silently repeat chargeable model work.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current jobs and idempotency](../development/jobs-and-idempotency.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0027](ADR-0027-identify-repeated-requests-by-caller-and-request-meaning.md), [ADR-0028](ADR-0028-recover-answer-requests-through-receipts-without-a-full-answer-replay-cache.md), [ADR-0029](ADR-0029-use-expected-revisions-to-protect-competing-changes.md).
