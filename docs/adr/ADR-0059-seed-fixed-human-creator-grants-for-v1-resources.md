# ADR-0059: Seed fixed human creator grants for v1 resources

**Status:** Accepted; supersedes [ADR-0057](ADR-0057-seed-explicit-reviewed-project-creator-grants.md).

**Date:** 2026-10-04

## Context and Problem Statement

Alice creates a Project and needs explicit authority to configure its ordinary resources and inspect feedback. The eleven-action seed did not cover these responsibilities. New Evaluation and query-inspection permissions also need deliberate resource initialization, rather than assuming a creator owns every future action.

## Considered Options

- Retain the smaller seed and obtain additional grants separately.
- Enumerate the additional Project and exact-resource assignments at creation.

The developer accepted the explicit expansion. An unrestricted administrator role remains excluded by bounded delegation.

## Decision Outcome

Seed the seventeen named Project actions and the fixed human creator assignments for each resource in [the initial-assignment contract](../development/access-contracts.md#initial-assignments). Pipeline creation assigns thirteen actions; Deployment creation assigns seven, including `feedback:write`. Source, Collection, connection, immutable profile and application-account assignments are separately enumerated.

All creator assignments are ordinary can-use-and-grant records committed with creation and audit. They do not grant document membership or authority on another resource. Private starter provisioning retains its separate admission boundary and explicit ordinary-resource initialization, without Organization Create projects authority.

## Consequences

- New human creators can administer the explicitly reviewed capabilities without a generic role or creator bypass.
- Existing resources are not automatically backfilled. Adding another action requires another explicit decision.
- Original retries recover creation without restoring subsequently removed grants.
- ADR-0057 preserves the rationale for the earlier eleven-action expansion; its list is historical.
- Application resource creation is deferred under ADR-0060. These assignments are accepted design, not migrations or runtime evidence.

## Links

- [Access control](../development/access-control.md#initial-project-grants).
- [Fixed identifiers and assignments](../development/access-contracts.md).
- [Logical Access records](../development/data-model.md#access).
- [ADR-0014: bounded delegation](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md).
- [ADR-0060: human provisioning](ADR-0060-keep-v1-resource-provisioning-human-only.md).
