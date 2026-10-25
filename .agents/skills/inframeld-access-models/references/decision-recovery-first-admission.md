# PD-ACCESS-04: Coordinate first account admission with identity recovery

**Status:** PENDING

**Owner:** `inframeld-access-models`

**Issue kind:** Implementation contract.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice has a verified Kratos identity but no local Principal. Recovery admits a block while an invitation is creating her first local account. A check that looks only for an organization-linked account can miss the race. Conversely, completing cleanup must not provision an account merely to find a lock.

Linked-account recovery uses existing organization coordination. Before the account exists, both workflows still need a common ordering rule around the exact installation/provider identity. That rule and its interaction with credential-state initialization have not been selected. A check followed by an unrelated insert can admit Alice across a newly created block.

## Accepted context and evidence

Recovery blocks exist independently of local product admission. Missing installation metadata is unavailable, not an empty/no-block result. First admission must respect current issuer authority and recovery state. Consent’s narrow credential-state initializer does not provision accounts or advance existing versions.

Preserve exact provider authority/subject and installation binding, organization-before-project lock ordering where applicable, short SQL transactions, unique identity links and the existing irreversible credential-version behavior. The identity-recovery completion service can finish for an identity without creating a local account.

## Alternatives and trade-offs

1. **Serialize through shared identity-scoped persistent coordination.** Have both admission and recovery coordinate on the same trusted provider identity before linking an account. This gives a visible ordering point before organization membership exists, but requires a real stable record or supported lock and an explicit lock order.
2. **Use conditional admission against versioned recovery observations.** Admission checks a captured state and conditionally commits only if it still holds, using the same protection for concurrent initialization. This can avoid a broad lock but requires a reliable comparison/constraint covering the absent-account case.

## Non-binding recommendation

**Proposal only.** Prefer the smallest identity-scoped coordination compatible with the existing credential-state and recovery records. Establish an explicit ordering point shared by both operations. Do not invent an account, grant or generic locking framework to obtain it.

## Decision trigger and stopping boundary

Before implementing first local admission, invitation activation/provisioning or recovery completion that can race with admission.

Pause the affected first-admission coordination only. Existing linked-human authentication and grant operations retain their current behavior.

## Architectural impact and dependencies

Access admission, invitations, identity links, recovery facts/repositories and credential-state initialization. Update first-admission and recovery sequence diagrams together. Database constraints remain design work until approved.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-03: Prove recovery cleanup before releasing product access](decision-recovery-production-completion.md). When production completion evidence or cleanup orchestration participates.

## Open questions and required evidence

- What exact record/condition serializes an identity before a Principal exists?
- How does it order with organization/project locks and version initialization?
- What outcome does a losing admission return and recover?
- How do two simultaneous first admissions avoid duplicate linkage without retrying unexpected work?

## Sources and finalization

- [Shared eligibility and first-admission qualification](eligibility-and-current-authority.md#shared-principal-eligibility).
- [Invitation authority](admission-and-invitations.md#invitations).
- [Completion workflow](recovery-completion.md#recovery-completion-workflow).
- [Credential query boundaries](eligibility-and-current-authority.md#credential-query-and-policy-boundaries).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
