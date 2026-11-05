# ADR-0128: Consolidate exact-target grant mutations

**Status:** Accepted. The target contract is selected, with POST retirement and remaining target integrations still requiring implementation and qualification. Supersedes the earlier requirement in the grant references to preserve the use-only POST indefinitely. Retains ADR-0068's focused aggregate and application-owned transaction decisions.

**Date:** 2026-11-05

## Context and Problem Statement

Alice gives Bob use-only permission to create access groups in Support. The implemented `POST /v1/projects/{project_id}/grants` performs that one creation operation and rejects any existing assignment. Exact-target PUT already supports creating or changing a Project action grant, and DELETE removes it. Keeping both mutation interfaces makes the same permission harder to explain and maintain before v1.

The difference is behavioral. Replacing an old POST with PUT can downgrade an existing use-and-grant assignment to use-only. An uncertain POST result therefore cannot be recovered by silently issuing PUT, even with the same visible retry key.

The developer approved the narrowed #226 issue and its endpoint-consolidation deliverable, then authorized reconciliation of the owning references during the backlog restructure. Access-owned administration should finish without waiting for every future resource to exist. Those future integrations remain required v1 work with their resource-feature owners.

## Considered Options

- Preserve the use-only POST alongside exact-target PUT/DELETE. This retains its published creation-only contract but leaves two interfaces for Project grant assignment.
- Consolidate mutations on exact-target PUT/DELETE before v1, deliberately migrate actual callers and retain original-operation history. This removes a duplicate interface while requiring explicit cutover and qualification.

These describe the current contract and selected replacement. No runtime benchmark or external-client migration study was performed for this decision.

## Decision Outcome

Use the concrete exact-target PUT and DELETE operations for grant mutations. Retire `POST /v1/projects/{project_id}/grants`, `assignProjectUseOnlyGrant` and its generated request/response exports together in the owning implementation. Preserve the exact-target GET and existing PUT/DELETE identities and semantics. Until that change is merged, POST and its current public examples remain supported descriptions of implemented behavior.

Migrate actual callers deliberately, including generated-client examples and qualification fixtures. Do not redirect or automatically transform an original POST into PUT. Changing an existing assignment requires the caller's explicit PUT intent, current authority and reviewed state. There is no selected compatibility wrapper or second grant API for v1.

Preserve stored original-operation identity, method, canonical route, fingerprint, expiry and outcome under the existing retention rules. Original-operation lookup remains read-only and subject to current authority for the original exact target/action. It may reveal only the retained permitted metadata. Retiring a route neither proves that an uncertain original failed nor permits redispatch as a new mutation. Missing or expired evidence retains its existing honest unknown outcome. This decision adds no historical write-replay route, retention extension or new lookup authority.

The #226 delivery boundary is complete grant administration for Organization, Project, access-group and application-account targets, together with their supporting own-access and eligible-recipient reads. Access owns grant meaning, eligibility, delegation, current authorization and handover safeguards. Each other resource feature supplies its real target tables and concrete grant integration under those same rules, including its target-specific routes and recipient discovery. Pipeline, Deployment, Collection, Source, model-connection and profile grant integration remains required with those owners. It is not deferred from v1 or absorbed into Access-only completion. Add no placeholder resource or generic registry to finish #226.

## Consequences

- The finished v1 interface has one mutation shape for exact-target grants, with the existing concrete operations and native OpenAPI generation.
- Removing POST intentionally removes its generated API surface. Implementation must update actual callers, public guidance and SDK qualification together, while preserving historical evidence.
- The duplicate-rejection behavior remains a fact about original POST operations. PUT's create/update behavior must not be presented as equivalent replay.
- Current eligibility, exact use-and-grant authority, expected revision, ordered locking, atomic grant/revision/audit/original-result persistence and safe last-grantor rules remain required.
- Access can complete its accepted targets before future resource integrations. Each receiving feature must retain explicit grant acceptance and real producer dependencies.
- This record changes documentation of the selected target. It neither removes a runtime route nor establishes automated or human qualification.

## Links

- [Grant administration and delivery boundary](../../.agents/skills/inframeld-access-models/references/grant-administration.md#exact-grant-management-and-bounded-reads).
- [Exact transport contracts and cutover](../../.agents/skills/inframeld-access-models/references/grant-contracts.md#grant-delivery-boundary-and-cutover).
- [Original request identity and recovery](../../.agents/skills/inframeld-application-contracts/references/idempotency-and-replay.md#requests).
- [ADR-0068: focused Project membership aggregate](ADR-0068-model-project-grants-through-project-membership-aggregates.md), whose aggregate and transaction rationale remain unchanged.
- [Access grant delivery #226](https://github.com/matejpalenik/inframeld/issues/226).
