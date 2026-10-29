# PD-ACCESS-06: Authorize setup details before a Deployment exists

**Status:** ACCEPTED on 2026-10-29 in [ADR-0111](../../../../docs/adr/ADR-0111-authorize-minimal-precreation-status-through-the-selected-pipeline.md). Implementation and qualification remain separate delivery work.

**Owner:** `inframeld-access-models`

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Contents

- [Approved resolution](#approved-resolution)
- [Why and example](#why-and-example)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Historical context and alternatives](#historical-context-and-alternatives)
- [Sources and finalization](#sources-and-finalization)

<a id="non-binding-recommendation"></a>

## Approved resolution

Use an explicit minimal Pipeline-authorized precreation setup projection through the shared default resolver. Require current eligible principal, Project membership and Query on the exact existing Pipeline named by the server-owned starter/default setup binding. Do not infer project-wide Query, scan for any visible Pipeline or trust a caller-supplied replacement target. Existing human/application eligibility and current credential checks apply. No new permission, placeholder Deployment or administrative MCP tool is introduced.

For that minimum view, expose only the authorized Project/Pipeline identities, the unbound logical default state and its safe revision, an overall safe setup category and a sanitized next-action category. Use the existing meanings such as incomplete configuration, permitted inputs required, preparing, failed, or explicit release required only when they can be established without revealing hidden resources. Otherwise use a generic unavailable/not-ready reason. Do not expose hidden source names/counts, excerpts, other callers' questions, raw provider errors or credential-presence details.

Other fields keep their ordinary independent authority. Configuration values need View configuration. Detailed job IDs/progress/errors require ordinary authorized operation/job inspection, including source disclosure checks. Other default group/collection/profile identities and names appear only where their owning read policy permits them. Secret metadata keeps its credential-management authority. Pipeline Query does not become a general job/history/configuration inspection grant. Suggest only a next action the caller is currently permitted to take, otherwise a safe request-for-help message without hidden manager identities.

If the setup Pipeline is absent, retired, invisible or inaccessible, do not construct it or reveal its identity. An inaccessible Project keeps the normal non-disclosing access response. An otherwise authorized but unavailable setup view returns only the permitted content-free outcome. Provisioning failure and deliberate removal remain distinct server-side facts; Query cannot repair them. Independent authorized setup/repair operations retain their own permissions and saved identities.

Once a real Deployment is bound, the resolver requires Query on that exact Deployment. Pipeline Query alone no longer authorizes default-serving/setup details. Neither grant implies the other. Ordinary creator grants are supplied only by the separately authorized atomic creation workflow, not copied from a Pipeline Query grant. The existing detailed operation/status APIs remain available only under their own current permissions.

Resolve binding state and authorize its selected projection consistently. If first publication or rebinding changes it before protected disclosure, re-evaluate using the new exact Deployment authority or return a safe changed/not-ready outcome without leaking the new target. Do not serve stale precreation details to bypass Deployment checks. After deliberate deletion, preserve removal history; an unbound route cannot automatically fall back to the original setup Pipeline's Query authority and expose/repair historical serving state. Repair uses its ordinary authorized workflow.

Before first readiness, the default query still rejects with the existing deployment-not-ready behavior before accepting a query, creating jobs/resources or making a model call. A temporary reservation rolls back. A setup read also performs no provider test, upload, preparation or automatic retry. HTTP, CLI, SDK and MCP use the same policy and sanitized meaning; finalized wire selectors remain normal interface-delivery work. This does not add a third MCP tool or turn query permission into Build, Create Deployment or Manage releases.

## Why and example

Alice has Query on her starter Pipeline, but the first build failed before any Deployment was created. Query on a nonexistent Deployment cannot authorize useful setup details. Bob guessing the Project ID must not learn the Project's state.

Alice can learn that her authorized starter Pipeline is not ready and that an authorized Build is the next step. Detailed build progress is shown only if she also passes the existing job-inspection checks. Bob has no Project/Pipeline access, so he learns neither that a build failed nor which resources exist. After first publication, Alice needs Query on the new Deployment; having Pipeline Query alone cannot bypass that transition.

Because the minimum setup view has an explicit existing authority, Alice can understand first-use failure without inventing a fake Deployment. Because richer fields keep separate checks, Query does not expose teammates' jobs or configuration. The alternative is always returning a generic not-ready result and requiring separate inspection. That is narrower, but makes setup harder to explain in CLI/MCP clients.

<a id="decision-trigger-and-stopping-boundary"></a>

## Apply the accepted contract

Use this contract when the original trigger matches. Do not ask for the same policy decision again. Concrete native methods, DTO names and physical schemas are implementation choices consistent with this contract and the repository conventions. Missing measurements, fixtures or assembled evidence block the affected qualification/support claim, not authorized implementation or isolated tests. A failed test is not permission to weaken an accepted safety boundary.

<a id="open-questions-and-required-evidence"></a>

## Implementation and required evidence

Pipeline Query only, Deployment Query only, no Project membership, suspended/revoked credentials, hidden/missing/retired setup Pipeline, forbidden detailed fields, first-publication/rebinding races, lost creation acknowledgment, deliberate deletion and HTTP/MCP parity. Demonstrate no query admission, resource repair, model call or permission transfer from a setup read.

These are required checks, not tests run or successful production evidence. No application edits, paid calls or production changes follow merely from recording this decision.

## Architectural impact and dependencies

Access policy/catalogue interpretation, onboarding/default resolver, Releases binding, HTTP/MCP status and CLI presentation. Update setup and first-publication sequences together. Any new public contract requires explicit review.

Load neighboring decisions only under these conditions:

- [PD-RELEASES-01 (accepted): Persist Deployment transitions with one shared control check](../../inframeld-releases/references/decision-deployment-state-and-concurrency.md). When implementing atomic first-ready creation and default binding.

## Historical context and alternatives

The following preserves the earlier problem, context and options. Statements that a choice was open describe that earlier analysis. The approved resolution above now settles it.

<a id="problem-and-example"></a>

### Original problem and example

Historical analysis before this resolution.

Alice has Query on her starter Pipeline. Its first build fails before a Deployment is created. The default resolver wants to show the failed build and next action. Bob can guess the project ID but has no access. The backend needs a named authority for Alice’s protected setup view while keeping Bob’s response non-disclosing.

Onboarding requires project membership plus Query before setup details are shown. Query is granted on an exact Pipeline or Deployment, and the grants do not imply each other. No Deployment exists yet in this example. The current text does not select the precreation target or protected projection.

### Original accepted context and evidence

Historical context before this resolution. Unchanged invariants still apply.

The default alias is unbound before first ready publication. A query cannot create resources or invoke a model to repair setup. Hidden projects remain hidden. First Deployment creation/binding and creator grants follow their accepted atomic rules.

Do not invent project-wide Query, a placeholder Deployment or an implicit Pipeline-to-Deployment grant. A generic content-free not-ready result differs from resource IDs, preparation details and safe next-action information that require authority. HTTP, CLI and MCP must share the chosen policy.

### Considered alternatives and trade-offs

Historical options, resolved by the approved contract above.

1. **Use an explicitly defined Pipeline-authorized setup projection.** Authorize the precreation view through the exact starter Pipeline’s Query grant and restrict it to the selected setup facts. This reuses existing authority, but must distinguish Pipeline setup from future Deployment reads and define the binding transition.
2. **Keep the default response generic and separate setup inspection.** Return only a safe generic not-ready outcome through the default path and expose details through an independently authorized existing-resource view. This keeps default resolution narrow, but requires clients to take a second step to explain setup.

## Sources and finalization

- [Default resolution](../../inframeld-architecture/references/first-use-and-private-defaults.md).
- [Exact Query permission](query-and-document-authorization.md#pipeline-query-authority).
- [Catalogue and initial assignments](actions-and-initial-grants.md#initial-assignments).
- [MCP defaults](../../inframeld-application-contracts/references/mcp-transport.md).

Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later change to this accepted policy. Qualification evidence must identify its artifacts, environment, failures and limits. This record does not fabricate implementation or a passing test.
