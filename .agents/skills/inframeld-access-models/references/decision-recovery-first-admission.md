# PD-ACCESS-04: Coordinate first account admission with identity recovery

**Status:** ACCEPTED on 2026-10-25 in [ADR-0082](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md). The shared coordinator and its three recovery/initialization participants are implemented. Complete first-admission integration and activation concurrency tests remain unfinished.

**Owner:** `inframeld-access-models`

**Issue kind:** Implementation contract.

This stable decision reference preserves the alternatives and approved resolution. [The coordination workflow](identity-admission-coordination.md) owns the current rule. The coordination workflow records the implemented subset separately from future first admission.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Accepted resolution](#accepted-resolution)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Implementation details and required evidence](#implementation-details-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice has a verified Kratos identity but no local Principal. Recovery admits a block while an invitation is creating her first local account. A check that looks only for an organization-linked account can miss the race. Conversely, completing cleanup must not provision an account merely to find a lock.

Linked-account recovery uses existing organization coordination. Before the account exists, both workflows need a common ordering rule around the exact installation/provider identity. The accepted identity lock below supplies that ordering. A check followed by an unrelated insert remains insufficient.

## Accepted context and evidence

Recovery blocks exist independently of local product admission. Missing installation metadata is unavailable, not an empty/no-block result. First admission must respect current issuer authority and recovery state. Consent’s narrow credential-state initializer does not provision accounts or advance existing versions.

Preserve exact provider authority/subject and installation binding, organization-before-project lock ordering where applicable, short SQL transactions, unique identity links and the existing irreversible credential-version behavior. The identity-recovery completion service can finish for an identity without creating a local account.

## Alternatives and trade-offs

1. **Serialize through shared identity-scoped coordination. Selected.** Have admission and recovery coordinate on the same trusted provider identity before linking an account. A PostgreSQL transaction-scoped advisory lock supplies the ordering point without requiring an existing row.
2. **Use conditional admission against versioned recovery observations. Not selected.** Admission checks a captured state and conditionally commits only if it still holds, using the same protection for concurrent initialization. This needs additional comparison/constraint and conflict-handling rules covering the absent-account case.

<a id="non-binding-recommendation"></a>

## Accepted resolution

The developer approved option A and its concrete design on 2026-10-25. [ADR-0082](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md) records an exclusive transaction-scoped advisory lock for the trusted installation/provider/subject. First admission, recovery admission/completion and credential-state initialization acquire this identity turn before organization/project locks, then reread current facts. Existing version safeguards, organization-before-project order, bounded database work and provider separation remain in force.

If recovery wins, a valid new invitation activation returns safe 409 with no account, consumption or assignments. If activation wins, recovery sees and blocks the newly linked account. Original-operation replay and unique identity links remain separate safeguards. [The owning workflow](identity-admission-coordination.md) explains failure handling and implementation limits.

## Decision trigger and stopping boundary

Before implementing first local admission, invitation activation/provisioning or recovery completion that can race with admission.

The coordination choice is settled. Implement affected paths against the accepted workflow after separate application-write approval. Existing linked-human authentication and grant operations retain their current behavior. The production completion contract is resolved under [PD-ACCESS-03](decision-recovery-production-completion.md), whose owning workflows record implemented native delivery, bounded cleanup, proof-backed release and host continuation. Complete first-local-admission integration and its concurrency qualification remain unfinished.

## Architectural impact and dependencies

Access admission, invitations, identity links, recovery facts/repositories and credential-state initialization. The [shared sequence diagram](identity-admission-coordination.md#follow-the-protected-database-step) covers first admission and recovery together. Existing uniqueness and foreign-key safeguards remain. This design selects no new table or schema change.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-03: Prove recovery cleanup before releasing product access](decision-recovery-production-completion.md). When production completion evidence or cleanup orchestration participates.

<a id="open-questions-and-required-evidence"></a>

## Implementation details and required evidence

- Implement one stable namespaced identity-key derivation and shared Access coordination boundary. Keep record access scoped to the full trusted identity.
- Verify actual PostgreSQL waiting for both admission/recovery orderings and initialization races. A request that began waiting before the other commit must read its committed changes afterward, using separate Read Committed statements. Keep provider calls outside transactions.
- Verify safe 409 leaves the invitation and account state unchanged, simultaneous activation preserves identity uniqueness and original-operation replay does not repeat effects.
- Verify timeout, cancellation and rollback release transaction-owned coordination without weakening version-history checks or the existing recovery deadlines.

## Sources and finalization

- [Shared eligibility and first-admission qualification](eligibility-and-current-authority.md#shared-principal-eligibility).
- [Invitation authority](admission-and-invitations.md#invitations).
- [Completion workflow](recovery-completion.md#recovery-completion-workflow).
- [Credential query boundaries](eligibility-and-current-authority.md#credential-query-and-policy-boundaries).
- [Accepted resolution](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md) and [owning coordination workflow](identity-admission-coordination.md).

This entry is resolved at its approved design scope. Follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later architectural change. Acceptance does not establish runtime qualification or authorize application writes.
