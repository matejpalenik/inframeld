# ADR-0113: Review exact case revisions and preserve generation shortfalls

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

Generating a question, editing it and approving it are different actions. Approval should apply only to what someone actually reviewed.

## Considered Options

- Use the focused bounded contract above. Selected.
- Provide a broad mutable save/accept operation, making exact review identity and partial outcomes less explicit.

## Decision Outcome

Apply the [complete accepted PD-EVALUATION-01 contract](../../.agents/skills/inframeld-evaluation/references/decision-case-review-contracts.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use focused generate, edit, review and benchmark-freeze operations with explicit expected state. Generation fixes Pipeline/Project, current admitted actor/source/audience scope, exact processed source versions/artifacts/spans, preset/seed, requested count, selected generator connection/model/settings and stable parent/child request identities. Starter generation requests 20 single-passage cases. The initial general bound is 1–100 requested cases per operation, with bounded original units rather than regeneration until the count is reached.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Narrow operations and explicit partial outcomes take more bookkeeping, but prevent unseen edits and failed generation from looking like accepted test coverage.

Alice reviews case C1 while Bob edits it into C2. Alice's stale approval conflicts. C2 is unreviewed, while an older benchmark still refers to its original exact revision.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-evaluation/references/decision-case-review-contracts.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
