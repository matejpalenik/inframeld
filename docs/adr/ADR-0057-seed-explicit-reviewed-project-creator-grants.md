# ADR-0057: Seed explicit reviewed project-creator grants

**Status:** Superseded by [ADR-0059](ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md). The eleven-action decision below preserves its original rationale; ADR-0059 owns the current seventeen-action Project seed and fixed resource assignments.

**Date:** 2026-10-04

## Context and Problem Statement

Alice creates Legal Research and must be able to administer its budget and tracing without gaining an unrestricted administrator role. The earlier project-creation contract assigned seven named project actions. CLI-first scope additionally requires separate budget inspection/management and tracing policy/history-deletion authority. The default list needs an explicit decision so adding a future action cannot silently broaden creator access.

## Considered Options

- Retain seven initial grants and obtain the four new policy/inspection grants separately. This preserves the old list but leaves the creator without the reviewed budget/tracing administration defaults.
- Add the four reviewed project actions as explicit grants. Creation remains bounded by a named list and normal action-specific checks.

These are the alternatives reviewed for this expansion. An open-ended administrator role is excluded by the existing bounded-delegation decision, not a newly evaluated option.

## Decision Outcome

Seed exactly eleven can-use-and-grant actions on the newly created project: Manage project members, Create access groups, Create application accounts, Create Pipeline, Create Deployment, Manage upload defaults, Delete project, `inspect-budget`, `manage-budget`, `manage-trace-policy` and `delete-trace-history`.

Preserve the published `create-access-groups` identifier. Exact wire identifiers for the remaining core display names still need specification. The owning [initial-grant contract](../development/access-control.md#initial-project-grants) records the live list; [the capability catalogue](../development/access-control.md#reviewed-capability-catalogue) records eligibility and extra checks.

Ordinary additional-project creation checks current human eligibility and organization-level Create projects authority, then commits project, creator membership, these grants, audit and original-request result together. An original retry cannot create another project or restore grants removed afterward. Private starter provisioning remains independent and neither requires nor grants organization-level Create projects.

## Consequences

- The creator has explicit budget/tracing authority on this project, subject to reviewed state and each workflow's safeguards. Those grants cover no other project or future unnamed action.
- No generic role or ongoing creator bypass is introduced; grants remain removable under ordinary handover rules.
- `inspect-feedback` is separately grantable and is not added to this seed. New resource-level Evaluation/inspection creator assignments remain open review work.
- GitHub requirements referring to seven initial grants need reconciliation. This documentation decision does not change issue bodies, code, migrations or generated schemas. Runtime qualification remains pending.

## Links

- [ADR-0014: bounded delegation](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md).
- [Access initial grants](../development/access-control.md#initial-project-grants), [onboarding](../development/onboarding.md#guided-setup-entry) and [Access records](../development/data-model.md#access).
- [#116: Access contracts](https://github.com/matejpalenik/inframeld/issues/116), [#28: ordinary administration](https://github.com/matejpalenik/inframeld/issues/28), [#27: private starter provisioning](https://github.com/matejpalenik/inframeld/issues/27).
