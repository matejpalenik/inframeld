# ADR-0032: Keep canary assignment stable for the same caller and affinity key

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

A canary exposes a candidate version to a limited group before promotion. Reassigning the same user on every request or when a key rotates would make behavior difficult to compare.

## Considered Options

- Deterministic logical assignment using stable caller, rollout, and affinity identities.
- Random routing for every request.
- Use a rotating credential or the current percentage as the cohort identity.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use the documented deterministic affinity scheme for a Deployment canary. Keep assignment stable for the same principal, rollout, and affinity key. Changing the canary percentage selects a threshold over that stable assignment. Affinity chooses routing; it does not establish identity or broaden document access. Canary operations require Manual releases.

**Example.** A busy caller may send many more requests than a quiet one. A 10% cohort therefore need not generate exactly 10% of traffic.

## Consequences

- A caller experiences a stable candidate assignment during a rollout, and credential rotation does not define a new caller.
- The required affinity input must be enforced. A percentage describes a share of identities, not an exact share of requests. Routing, promotion, rejection, rollback, and current-access races require qualification.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current pipelines and releases](../development/pipelines-and-releases.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0033](ADR-0033-separate-build-readiness-from-release-authority.md).
