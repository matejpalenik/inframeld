# ADR-0027: Identify repeated requests by caller and request meaning

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

A caller can lose a response after work was accepted. Retrying must find the same operation rather than create duplicate work, while reuse of a key for a different request must be rejected.

## Considered Options

- Durable scoped idempotency records tied to stable caller and request meaning.
- Treat every retry as a fresh operation.
- Use a key alone without checking its scope and payload meaning.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Persist the accepted operation and its idempotency relationship atomically. Match stable caller, scope, key, and request meaning; reject same-key/different-meaning conflicts. Reauthorize replay and return the recorded outcome appropriate to its state. Secret-bearing inputs use keyed fingerprints. Default-route retries find the original operation before resolving a newly changed target.

**Example.** A retry of query Q with key K must not become a new paid query merely because the project’s default deployment changed after the first request.

## Consequences

- Lost responses can be recovered without silently repeating admitted work or redirecting a retry to another resource.
- Guarantees depend on retained authoritative history. Concurrent in-progress requests, expired history, uncertain external outcomes, and secret-bearing responses need their documented handling.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current jobs and idempotency](../development/jobs-and-idempotency.md).
- [Current mcp](../development/mcp.md).
- [Current onboarding](../development/onboarding.md).
- Related decisions: [ADR-0026](ADR-0026-persist-background-work-through-controlled-durable-attempts.md), [ADR-0028](ADR-0028-recover-answer-requests-through-receipts-without-a-full-answer-replay-cache.md), [ADR-0029](ADR-0029-use-expected-revisions-to-protect-competing-changes.md).
