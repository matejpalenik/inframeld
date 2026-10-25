# PD-ACCESS-06: Authorize setup details before a Deployment exists

**Status:** PENDING

**Owner:** `inframeld-access-models`

**Issue kind:** Architecture and protected-read contract.

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

Alice has Query on her starter Pipeline. Its first build fails before a Deployment is created. The default resolver wants to show the failed build and next action. Bob can guess the project ID but has no access. The backend needs a named authority for Alice’s protected setup view while keeping Bob’s response non-disclosing.

Onboarding requires project membership plus Query before setup details are shown. Query is granted on an exact Pipeline or Deployment, and the grants do not imply each other. No Deployment exists yet in this example. The current text does not select the precreation target or protected projection.

## Accepted context and evidence

The default alias is unbound before first ready publication. A query cannot create resources or invoke a model to repair setup. Hidden projects remain hidden. First Deployment creation/binding and creator grants follow their accepted atomic rules.

Do not invent project-wide Query, a placeholder Deployment or an implicit Pipeline-to-Deployment grant. A generic content-free not-ready result differs from resource IDs, preparation details and safe next-action information that require authority. HTTP, CLI and MCP must share the chosen policy.

## Alternatives and trade-offs

1. **Use an explicitly defined Pipeline-authorized setup projection.** Authorize the precreation view through the exact starter Pipeline’s Query grant and restrict it to the selected setup facts. This reuses existing authority, but must distinguish Pipeline setup from future Deployment reads and define the binding transition.
2. **Keep the default response generic and separate setup inspection.** Return only a safe generic not-ready outcome through the default path and expose details through an independently authorized existing-resource view. This keeps default resolution narrow, but requires clients to take a second step to explain setup.

## Non-binding recommendation

**Proposal only.** Prefer an explicit Pipeline-authorized setup projection where the starter Pipeline exists, with a clearly defined transition to exact Deployment authority. Compare the alternative’s simpler resolver against the junior user’s need to understand a failed first build. This is not yet a new permission or endpoint.

## Decision trigger and stopping boundary

Before defining defaults/setup read contracts or implementing HTTP/MCP/CLI prepublication status resolution.

Pause only the protected precreation projection and authority choice. Existing resource Query checks and accepted first-publication behavior stay fixed.

## Architectural impact and dependencies

Access policy/catalogue interpretation, onboarding/default resolver, Releases binding, HTTP/MCP status and CLI presentation. Update setup and first-publication sequences together. Any new public contract requires explicit review.

Load neighboring decisions only under these conditions:

- [PD-RELEASES-01: Persist Deployment transitions with one shared control check](../../inframeld-releases/references/decision-deployment-state-and-concurrency.md). When implementing atomic first-ready creation and default binding.

## Open questions and required evidence

- Which exact resource authorizes each precreation field?
- What can safely be returned when no Pipeline is visible or provisioned?
- When does the authority switch to the created Deployment?
- How are inaccessible setup states and lost first-publication responses represented without leaks?

## Sources and finalization

- [Default resolution](../../../../docs/development/onboarding.md).
- [Exact Query permission](../../../../docs/development/access-control.md#pipeline-query-authority).
- [Catalogue and initial assignments](../../../../docs/development/access-contracts.md#initial-assignments).
- [MCP defaults](../../../../docs/development/mcp.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/documentation-maintenance.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
