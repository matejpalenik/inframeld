# ADR-0124: Authorize Project metadata changes explicitly

**Status:** Accepted. Partially supersedes [ADR-0059](ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md), only its Project creator list/count.

**Date:** 2026-10-30

## Context and Problem Statement

Alice must allocate or rename an existing Project’s exact selector without changing its permanent ID or receiving unrelated authority. The existing unrestricted text label cannot be silently reinterpreted as a selector. The prior seventeen-action creator seed has no metadata action, and existing Projects may have no eligible grantor for a newly added action.

The developer explicitly approved the reviewed naming/security design and its listed guide/ADR updates on this date. This decision leaves settled identity, scope, exactness, non-reuse, atomicity and safety-metadata retention policy intact.

## Considered Options

- Keep unrestricted inputs, or select bounded exact Names and submitted replacement labels. Bounds make new metadata predictable while retaining legacy values losslessly.
- Reserve additional words, or retain useful names such as `production` without an extra list.
- Automatically apply generated suggestions, or present previews requiring explicit valid input.
- Borrow creation/membership authority or creator history, or add a least-privilege exact-Project action with explicit grants.
- Backfill existing Projects, defer them to unspecified recovery, or deliver the narrow accepted host-repair subset needed for the first grant.

## Decision Outcome

Select exact Names of 1–63 lowercase ASCII letters/digits/hyphens, starting with a letter and ending with a letter/digit. Add no reserved words. Submitted replacement Display names contain 1–128 Unicode code points and satisfy the owning whitespace/control rules. Suggestions are previews only. Preserve unrestricted legacy labels exactly on migration, reads, replay and selector-only updates. Allocate the first selector explicitly through the permanent ID. Lookup never silently normalizes input.

Add human-only `edit-project-metadata` on one exact Project for first selector allocation and Name/Display-name changes. It is the eighteenth explicit creator can-use-and-grant assignment for ordinary Projects and private starters. All other ADR-0059 creator assignments, no-backfill, atomicity and replay rules remain accepted. Organization bootstrap retains four grants. Automatic creator seeding remains selected design for #223 ordinary creation and #27 private starters, not an implemented #120 guarantee.

#120 must deliver current metadata authorization and the restricted `repair-stranded-authority` host path for this exact Project action. Host execution supplies authority. Current independently verified recipient proof, installation binding, membership, stranded state and expected Access revision constrain the repair. Persist the assignment, revision, audit and typed receipt together. Replay verifies current proof/recipient eligibility and returns the original outcome without restoring removed grants. Preserve recovery-continuation behavior and shared cross-mode request uniqueness.

Use a production-used typed scoped resolver with a real Project adapter and current Access visibility. Validate returned kind, scope and exact Name. Controlled same-spelling Collection/Profile bindings test the same resolver’s wrong-kind/wrong-Project boundary without claiming their future CRUD. Metadata writes retain permanent IDs, require current authority and expected metadata revision, and save name reservation, change, audit and original outcome atomically.

## Consequences

- Project metadata has a precise human-only permission and a deliverable first-grant recovery path, without broader grants or creator bypasses.
- New creation owners must explicitly assign eighteen actions. Existing Projects receive no automatic backfill. Removed grants remain removed after replay.
- Legacy label compatibility costs remain explicit. New submission validation must not become response validation that rejects retained values.
- #120 requires real Project resolution/rename/repair, concurrency, rollback, revocation, original-ID recovery and cross-kind qualification. Recording alone is incomplete delivery.
- Backend code, migrations, public HTTP/OpenAPI, generated SDKs and production qualification remain unfinished at this recording checkpoint. General grant administration, full CLI context and future resource provisioners remain separately owned.

## Links

- [Approved Project metadata decision and full acceptance](../../.agents/skills/inframeld-access-models/references/decision-project-metadata-authority.md).
- [Exact naming and identity](../../.agents/skills/inframeld-architecture/references/resource-names-and-identity.md#resource-naming).
- [Actions and explicit initial grants](../../.agents/skills/inframeld-access-models/references/actions-and-initial-grants.md#initial-assignments).
- [Narrow Project metadata repair](../../.agents/skills/inframeld-access-models/references/host-maintenance.md#project-metadata-authority-repair).
- [Accepted retention/erasure policy](../../.agents/skills/inframeld-knowledge/references/decision-retention-erasure-policy.md).
- [ADR-0059 historical creator expansion](ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md).
