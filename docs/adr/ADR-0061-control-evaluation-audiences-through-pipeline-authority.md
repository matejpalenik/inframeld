# ADR-0061: Control Evaluation audiences through Pipeline authority

**Status:** Accepted.

**Date:** 2026-10-04

## Context and Problem Statement

SupportBot imports HR test questions and reference answers before their sources are linked. Those contents already need protection. Editing authority must not let a bot decide to share them with SupportKnowledge, yet requiring a human to perform every import would prevent the accepted automation workflow.

## Considered Options

- Give audience administration its own Pipeline-scoped human capability and save an approved audience for automated imports.
- Use finer permission records on individual test cases.

The developer selected Pipeline-scoped grants and accepted a saved human-managed import audience. Existing source protections remain cumulative.

## Decision Outcome

Use human-only `manage-evaluation-case-audiences` on the exact Pipeline. The caller must manage every group in the authoritative current and proposed audiences. The operation may change the nonempty project-local future-import audience or explicitly selected existing cases' audiences.

Applications with case-editing authority may import into the saved current human-approved audience; they cannot select or override another audience. Persist protection before source linking. Changing the default affects future imports only. Existing-case changes require a separate explicit reviewed operation, current authority and expected-state checks.

The [Evaluation guide](../development/evaluation.md#case-audiences) owns the procedure; [the data model](../development/data-model.md#evaluation) owns logical records. Neither the audience nor Pipeline grants replace current linked-source access.

## Consequences

- Case editing, content review and audience administration remain distinct responsibilities.
- No grant row per case or new Dataset/Experiment resource is introduced.
- Stale audience review fails rather than silently substituting or widening protection.
- New/changed content remains unreviewed. An audience change is not content acceptance.
- Physical schema, exact wire fields and runtime qualification remain delivery work.

## Links

- [Fixed Access actions](../development/access-contracts.md#capability-catalogue).
- [ADR-0015: separate audience and operation access](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md).
- [ADR-0049: managers are members](ADR-0049-require-group-managers-to-be-ordinary-members.md).
