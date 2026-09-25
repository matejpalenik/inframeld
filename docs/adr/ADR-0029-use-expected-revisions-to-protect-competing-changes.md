# ADR-0029: Use expected revisions to protect competing changes

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

An idempotency key distinguishes retries of one command. It does not prevent a different command, based on stale state, from overwriting a newer change.

## Considered Options

- Expected revisions in addition to idempotency keys.
- Use last-write-wins or assume different retry keys make competing edits safe.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Check the expected revision for revision-controlled state changes and reject a stale competing command. Preserve the existing operation’s outcome on a retry with its original identity. Use the owning feature’s revision boundary; Access scope revisions and Deployment control revisions serve their documented different state boundaries.

**Example.** Two operators read revision 3. After one successfully changes the record, the other’s new command based on revision 3 conflicts rather than overwriting it.

## Consequences

- A user can learn that the state changed instead of silently overwriting another user’s decision.
- Clients must distinguish a retry from a new edit and surface conflicts honestly. Revision checks do not replace current authorization or external-attempt fencing.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current jobs and idempotency](../development/jobs-and-idempotency.md).
- [Current pipelines and releases](../development/pipelines-and-releases.md).
- [Current model connections](../development/model-connections.md).
- Related decisions: [ADR-0026](ADR-0026-persist-background-work-through-controlled-durable-attempts.md), [ADR-0027](ADR-0027-identify-repeated-requests-by-caller-and-request-meaning.md), [ADR-0028](ADR-0028-recover-answer-requests-through-receipts-without-a-full-answer-replay-cache.md).
