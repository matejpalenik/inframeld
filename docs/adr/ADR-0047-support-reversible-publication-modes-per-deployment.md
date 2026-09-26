# ADR-0047: Support reversible publication modes per Deployment

Status: Accepted

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
