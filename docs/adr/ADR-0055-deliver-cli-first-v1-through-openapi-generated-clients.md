# ADR-0055: Deliver CLI-first v1 through OpenAPI-generated clients

**Status:** Accepted; partially supersedes ADR-0006's external tooling prerequisite.

**Date:** 2026-10-01. This is the recording date; the exact date of the earlier delivery agreement was not recorded.

## Context and Problem Statement

Alice should be able to install Inframeld, sign in, configure models, prepare documents, experiment, evaluate and release a pipeline without waiting for a full browser Studio. Human sign-in still needs a small, secure account UI. The existing backlog mixed that necessary UI with the deferred Studio and tied generated clients to a separate tooling project.

The accepted CLI decisions now define v1 behavior. Keeping a competing Studio-first release chain would delay that experience and leave two inconsistent product specifications.

## Considered Options

- Deliver Studio first and retain the earlier external client-tooling prerequisite.
- Deliver a Rust CLI and the required Ory account UI first, using clients generated from the backend's authoritative OpenAPI contract.
- Handwrite parallel clients or weaken the backend contract to fit a generator.

## Decision Outcome

Select CLI-first v1 with the small Kratos/Hydra account UI, not a full Studio. Generate application clients from native FastAPI OpenAPI 3.1.x. No generator package is selected by this decision. Qualify the selected implementation against the actual schema and runtime behavior, starting with implemented foundations and extending coverage as features arrive. Backend development does not wait for Studio or a separate generator project.

Keep Studio epics and issues for a later version. They must consume the same backend contracts and follow the accepted CLI-led model, evaluation, query/build/release, access and recovery behavior. Browser account integration may use official Ory clients for Ory's own contracts; that is not a competing Inframeld client.

Assign all non-Studio existing and new delivery issues, including completed foundations, to the existing v1 milestone. A v1 issue cannot depend directly or transitively on deferred Studio work. Preserve completed status and interface-only `PipelineHook` / `WebhookDispatcher` planning; executable hooks, subscriptions and delivery services remain excluded.

## Consequences

- CLI and account-UI qualification replace Studio qualification on the v1 release path. Upgrade, backup/restore, MCP, security and measured capacity gates remain.
- Shared output, automation, context, cancellation and recovery contracts require explicit CLI implementation and qualification, not duplicated domain logic in Rust.
- Generated-client compatibility is measured per supported client and feature; intended language targets are not automatically supported deliverables.
- The backlog and [delivery plan](../development/cli-delivery-plan.md) track accepted decisions, unresolved specification prerequisites and evidence. This documentation is not runtime qualification.

## Links

- [ADR-0006](ADR-0006-use-official-generated-clients-for-application-api-access.md), whose generated-client and thin-transport rationale remains.
- [API contracts](../development/api-contracts.md) and [deployment](../development/deployment.md).
- [CLI v1 delivery epic](https://github.com/matejpalenik/inframeld/issues/114) and [Definition of Done](../development/definition-of-done.md).
