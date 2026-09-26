# ADR-0033: Separate build readiness from release authority

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Preparing a pipeline version and deciding whether it should answer customer requests have different owners and permissions. A completed build must not acquire release authority merely by finishing.

## Considered Options

- Build complete ready bindings, then perform a separately authorized publication transition.
- Move live traffic whenever a build completes.
- Let evaluation or feedback scores independently authorize publication.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Have ordinary builds publish readiness, not Deployment serving pointers. Releases selects ready compatible versions through its authorized transitions. Automatic updates may authorize ordinary build and separate conditional publication in advance, but must retain their current authority and control checks. Human creation has the accepted first-ready-version and explicit creator-grant transaction.

**Example.** P13 can finish successfully after the user switches to Manual releases. It remains a usable ready result, but the old automatic operation cannot publish it.

## Consequences

- Engineers can prepare and compare versions without accidentally changing customers’ answers.
- Publication needs its own state, permission, readiness, and concurrency checks. A ready result may remain unpublished after a mode change or newer request.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current pipelines and releases](../development/pipelines-and-releases.md).
- [Current onboarding](../development/onboarding.md).
- [Current access control](../development/access-control.md).
- Related decisions: [ADR-0032](ADR-0032-keep-canary-assignment-stable-for-the-same-caller-and-affinity-key.md).
