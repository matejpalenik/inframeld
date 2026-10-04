# ADR-0047: Support reversible publication modes per Deployment

Status: Accepted; partially superseded by [ADR-0052](ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md).

ADR-0052 replaces the configuration Save and apply interaction with direct Pipeline querying/evaluation followed by a user-facing Build of the saved configuration. The original rationale below is preserved. Reversible modes, authorized automatic document updates, first-publication rules and publication guards remain current; working edits and direct-query preparation never authorize publication.

**Date:** 2026-09-19

## Context and Problem Statement

New users need prepared knowledge to become useful without manually performing every release step, while engineers also need deliberate comparison, canary, and rollback workflows.

## Considered Options

- Automatic updates and Manual releases as reversible per-Deployment modes.
- A one-time first-publication gate or separate quickstart engine.
- Automatic promotion based on evaluation scores or every uploader’s activity.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Make publication mode a Deployment property. The default onboarding path starts in Automatic updates; explicitly created deployments default to Manual releases with an automatic option. Automatic operations freeze authorized inputs, perform normal build, then conditional publication under current authority and captured control/request/attempt state. Switching modes invalidates old publication authority. Canaries and rollback require manual mode.

**Example.** Switch automatic to manual and back. The old job’s mode label may match again, but its control revision is stale. Enabling automatic authorizes a fresh update instead.

[ADR-0054](ADR-0054-use-shared-current-model-connections.md) distinguishes shared connection administration from Pipeline publication. Both modes use current connection access settings. Connection managers may update them after the separate guarded review; Manual mode does not prevent this and Pipeline rollback does not restore connectivity. Existing release permissions, mode guards and document-update rules remain unchanged.

## Consequences

- A simple first-use path and deliberate release control share ordinary resources and application behavior.
- Concurrent uploads, mode changes, first creation, deletion/rebinding, and newer failed requests require careful checks. Old work cannot revive after an off/on switch, and Compare neither pauses automatic updates nor authorizes publication.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current pipelines and releases](../development/pipelines-and-releases.md).
- [Current onboarding](../development/onboarding.md).
- [Current access control](../development/access-control.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0046](ADR-0046-provision-creator-private-defaults-through-ordinary-resources.md).
