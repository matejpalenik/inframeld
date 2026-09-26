# ADR-0046: Provision creator-private defaults through ordinary resources

Status: Accepted

**Date:** 2026-09-19

## Context and Problem Statement

A new contributor should be able to configure models, upload documents, and ask a useful question without first learning every internal resource. Convenience must not introduce a parallel security or serving model.

## Considered Options

- Private starter resources and default bindings using normal application behavior.
- Require manual organization, project, group, collection, and pipeline setup before the first answer.
- Use a separate quickstart engine or installation-wide public knowledge pool.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Provision the admitted human’s private starter project, group, and normal setup resources through controlled, repeatable workflows. Securely claim the first administrator through operator-controlled bootstrap. Use ordinary scope, grants, readiness, and serving rules, with no implicit administrator read bypass or placeholder Deployment. The separate publication-mode decision governs automatic and manual behavior.

**Example.** Alice receives private starter access. Bob’s admission creates his own defaults; it does not add him to Alice’s document groups.

## Consequences

- New users can follow a short product journey while later work uses the same identities and invariants.
- Provisioning retries, explicit creator grants, not-ready states, default deletion/rebinding, and first publication require careful implementation. The first-answer timing goal remains flexible and unmeasured.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current onboarding](../development/onboarding.md).
- [Current access control](../development/access-control.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0047](ADR-0047-support-reversible-publication-modes-per-deployment.md).
