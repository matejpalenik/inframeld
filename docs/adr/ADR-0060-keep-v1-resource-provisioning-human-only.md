# ADR-0060: Keep v1 resource provisioning human-only

**Status:** Accepted.

**Date:** 2026-10-04

## Context and Problem Statement

SupportBot can update an existing Pipeline through explicit grants. Allowing it to create another would require a separate decision about which human receives grant-administration responsibility, because applications receive use-only rights. This is a delivery-scope choice, not a technical inability to authenticate application creation requests.

## Considered Options

- Allow eligible application creation with a human-approved resource initialization binding.
- Keep configurable resource creation human-only in v1 while retaining application-driven updates and operations.

The developer reconsidered both alternatives and selected the latter for now.

## Decision Outcome

Keep Project/resource provisioning human-only as enumerated in [the provisioning contract](../development/access-contracts.md#provisioning). Applications may perform supported updates and operational work on existing resources with explicit eligible grants. Versions, Documents, jobs and Evaluation cases produced by those operations remain permitted workflow output.

Application configuration imports may reuse existing compatible resources and apply eligible updates. A plan requiring resource creation is ineligible; reject it before known-invalid mutations and identify the necessary human step. Human-only administration remains human-only through imports, with no saved-human fallback.

## Consequences

- V1 avoids the extra application-creation initialization contract while preserving automated sync, builds, evaluation and release workflows on existing resources.
- A human must provision missing resources and changed immutable profiles before an application can use them.
- Automatic update mode does not grant creation authority or bypass first-Deployment human provisioning.
- Application-driven resource creation is deferred for later review, with no speculative interface or schema introduced now.

## Links

- [Access workflow authority](../development/access-control.md#cli-automation-authority).
- [Configuration import](../development/configuration-portability.md#destination-review).
- [ADR-0016: shared principals](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md).
- [ADR-0059: fixed creator grants](ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md).
- Implementation and qualification remain pending; this decision does not alter application code.
