# Current permissions and bounded administration

<a id="current-permissions-and-bounded-administration"></a>

Alice and SupportBot both belong to Support, but only SupportBot has Query on Production. Alice's membership does not supply that missing grant. Carol can manage releases without automatically reading every document. Access keeps these relationships separate so administration does not become an implicit data-reading bypass.

<a id="concepts-and-owners"></a>

## Choose a focused reading task

- For current eligibility and typed evidence, read [Eligibility and current authority](eligibility-and-current-authority.md).
- For query authority and permitted evidence, read [Query and document authorization](query-and-document-authorization.md).

## Concepts and owners

A product operation asks whether the principal is eligible now, belongs to the project, may perform the exact action on the target and may read any required documents. Default to denial. Groups or permissions supplied by the caller cannot establish authority.

A grant records an action that a recipient may perform on a target. It can permit use or use-and-grant. The latter allows delegation, which means giving that exact action on that exact target to someone else. Applications may receive eligible use grants, never human-only administration or delegation.

The shared schema stores current grants in target-specific tables, with one recipient/action/target assignment and a `can_grant` value. Audit history is separate from these current assignments.

Group membership supplies document reading through an explicit allowlist. Management supplies sharing authority. Managers are peers, with no privileged owner above them. Every manager must also have ordinary membership in the same group.

Appointing a manager records both relationships. Demotion removes management while keeping membership. Removing membership also removes management in the same transaction. Rejoining does not restore management automatically. Action grants have their separate lifecycle.

<a id="follow-a-grant-change"></a>

## Follow a grant change

1. Authenticate before the write transaction. The Access service loads current facts in the caller's transaction under the accepted organization/project lock protocol.
2. Interpret authentication evidence before visibility or replay. Reject a stored principal-kind mismatch as an internal contract error. Reject stale human OAuth evidence with the generic invalid-token outcome.
3. Apply project visibility before disclosing authority or recipient existence. Hidden projects remain 404. For visible projects, missing eligibility, recovery restrictions or authority produce the documented denial. Check the actor before revealing an absent recipient.
4. Require an eligible human grantor with exact delegation authority. The complete grant service also checks returned project scope against the unchanged Command before idempotency reservation or replay. A mismatch is an internal runtime failure that rolls back and receives the generic HTTP 500.
5. For new work, load the recipient's membership in checked scope and verify organization, project and recipient. Invoke `ProjectMembership.assign_use_only_grant()`, save with the checked project-wide revision and original operation ID, then commit required audit and completion together.

The shared eligibility policy owns common account/recovery decisions. Operation policies add their own requirements. Access services own current reads and failure ordering. Target-specific persistence does not create separate policy implementations.

Facts readers can compose efficient SQL expressions, but must not instantiate another executing reader merely to fill a facts field. Grant, scope-revision and account-status mutations all follow the accepted lock protocol. Application-owned grant transactions and caller-bound admission helpers retain distinct transaction ownership.

<a id="aggregate-and-persistence-boundary"></a>

## Aggregate and persistence boundary

`ProjectMembership` owns one recipient's direct project grants. Its identity is project plus principal. Immutable `ProjectActionGrant` children identify project, recipient and action. The aggregate rejects duplicate assignment at either level and application delegation. The supported workflow adds attributed use-only grants without replacing historical values.

Its specific repository loads existing membership only. It neither provisions membership nor authorizes, commits, acquires locks or retries. Save additions with one conditional project-wide revision increment and required audit. Membership creation, revocation and cross-member lifecycle operations remain deferred.

Loaded objects and their immutable snapshots belong to one active transaction. Bind the exact instances to that transaction. Preserve timestamps and attribution, and compare child values independently of entity identity. Discard the instances after the transaction ends or a save fails so a later attempt starts from current state.

<a id="administration-and-document-audiences"></a>

## Administration and document audiences

Do not infer permission from a title, creator history, installation administration or membership. Fixed creator assignments are explicit grants, not permanent authority. The accepted catalogue defines seventeen initial additional-Project actions, thirteen Pipeline actions and seven Deployment actions. The historical eleven-action seed is superseded. Existing resources receive no automatic backfill.

An audience is the set of groups permitted to read protected material. Document audiences, source/imported-case audiences and upload defaults need deliberate authorized destination groups. Imported metadata and upstream access-control lists cannot grant access.

Query on a Pipeline uses its working settings, while Query on a Deployment uses serving selection. Neither grants the other. Query-trace inspection requires its own grant on the exact resource and current source access, including other callers' answers. There is no Experiment resource.

After successful Query authorization, an empty permitted source set takes the ordinary no-evidence path without Chroma search. A forbidden query, an empty saved document allowlist or lost permission to a protected evidence bundle still denies the relevant operation. Never disguise denial as a successful empty read.

<a id="traces-feedback-and-evaluation-evidence"></a>

## Traces, feedback and evaluation evidence

Trace inspection can be explicitly granted to eligible humans or applications, with current source checks. Project tracing/retention changes are human-only, and explicit history deletion needs separate human deletion authority. Query, inspection and policy management are different grants. Recording does not depend on the caller's inspection rights.

Imports can preserve destination policy, but restricted explicit apply must be denied without identity fallback. Automatic expiry and source erasure do not need new human approval for each record. These query-inspection rules grant no unspecified non-query history access.

CLI feedback includes authorized reports and correction of the originating principal's own live-answer rating. Reports do not authorize changing someone else's rating. Current evidence checks filter totals as well as comments.

Evaluation has six exact-Pipeline use permissions for eligible humans and applications. Human case-audience administration and fixed creator assignments remain separate. Generated cases inherit source protections. Check current access before sending data to a model and again before later disclosure.

Ragas receives no credentials or independent provider clients. Generator/judge bindings may reuse authorized connections without another key, but never imply a model/provider fallback.

<a id="departure-invitations-and-host-maintenance"></a>

## Departure, invitations and host maintenance

Ordinary departure preserves required management. Emergency suspension immediately blocks even a sole manager while preserving relationship records. Scoped operator recovery explicitly assigns membership and management to an eligible replacement without reviving the compromised account or granting unrestricted reading. Each project, resource, document, group and application-account deletion has separate permissions and reference rules.

Invitation admission rechecks verified identity and current issuer authority for its exact assignments.

Host maintenance supplies its own narrow authority. The version 1 maintenance draft uses a transient Hydra human token only for independent candidate-identity checks. Host execution authorizes the operation. Ordinary login cannot become host authority. Keep session budgets, mutation limits, invitation, grant-listing, private recovery and maintenance inputs under their exact contracts.

<a id="status-and-authoritative-routes"></a>

## Status and authoritative routes

Access policy remains application-owned in PostgreSQL. OpenFGA and PyCasbin were considered but not selected. Follow the [recorded reconsideration criteria](#section-introduce-a-general-authorization-engine-or-policy-language-now) before proposing a generic policy language, speculative adapter or authorization cache.

The 14-table foundation enforces selected scoped relationships, manager membership, resource/principal kinds, uniqueness and application use-only grants. The action catalogue is not yet enforced by database checks. Grant tables for future resource kinds do not authorize implementing those domains now. Most administration, audit-retention and physical/wire workflows still need implementation or qualification.

The fixed catalogue is accepted design. Downstream draft routes and production qualification remain explicitly separate.

The supported use-only human project grant is the complete reference workflow. Both grant-facts and linked recovery-admission adapters use fixed five-second database deadlines including lock waits, leaving rollback to the caller. The [typed authorization capabilities](eligibility-and-current-authority.md#typed-authorization-capabilities) and the [transaction/service chain](../../inframeld-application-contracts/references/transactions-jobs-and-idempotency.md) explain the shared contracts. Type conformance alone cannot prove ordering before disclosure or mutation.

- [Access control](./authorization.md), [bounded administration](memberships-groups-and-handover.md#section-bound-administration-grants-and-recovery), [shared eligibility](eligibility-and-current-authority.md#shared-principal-eligibility), [group managers](memberships-groups-and-handover.md#group-managers), [query authority](query-and-document-authorization.md#pipeline-query-authority) and [maintainer checks](#maintainer-checks).
- [Trace authority](../../inframeld-pipelines/references/query-tracing-and-privacy.md#trace-authority), [trace lifecycle](../../inframeld-pipelines/references/query-tracing-and-privacy.md), [feedback authority](../../inframeld-pipelines/references/answer-feedback.md#authorization), [Evaluation permissions](../../inframeld-evaluation/references/generation-and-review.md#operation-authority), [case audiences](../../inframeld-evaluation/references/case-audiences.md#case-audiences) and [non-query diagnostic deferral](../../inframeld-pipelines/references/query-tracing-and-privacy.md#non-query-diagnostics).
- [Access contracts](actions-and-initial-grants.md), [catalogue and assignments](actions-and-initial-grants.md#initial-assignments), [invitations](admission-and-invitations.md#invitations), [maintenance](host-maintenance.md#maintenance) and [remaining work](#review-and-remaining-work) preserve the accepted review's scope and closed historical tracking status without claiming downstream completion.
- [Access records](identity-and-grant-records.md#access), [manager constraint](access-lifecycle-persistence.md#group-manager-membership-constraint), [write coordination](grant-administration.md#how-the-database-gives-each-change-its-turn), [grant chain](../../inframeld-coding-standards/references/services-and-use-cases.md#grant-command-flow) and [membership repository](../../inframeld-coding-standards/references/aggregates-and-repositories.md#membership-aggregate-and-repository).
- Rationale: [application-owned policy](../../../../docs/adr/ADR-0013-keep-authorization-in-access-and-postgresql.md), [bounded delegation](../../../../docs/adr/ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [document groups](../../../../docs/adr/ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [emergency recovery](../../../../docs/adr/ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [manager membership](../../../../docs/adr/ADR-0049-require-group-managers-to-be-ordinary-members.md), [creator grants](../../../../docs/adr/ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md), [shared eligibility](../../../../docs/adr/ADR-0064-centralize-principal-eligibility-and-keep-access-aggregates-focused.md) and [membership aggregate](../../../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md).

<a id="three-separate-checks"></a>

<a id="the-model"></a>

<a id="1-three-separate-checks"></a>

## Three separate checks

Alice works in **Support**, a project containing documents, pipelines, and access settings. The project has two **access groups**, `SupportKnowledge` and `HRPrivate`. Each group identifies people or applications who may read documents shared with it. It does not bundle permissions such as uploading or publishing.

Each document lists the groups allowed to read it. This list is its **group allowlist**. Membership in any listed group supplies document access, provided the caller still belongs to the project and is allowed to act.

The **Support Pipeline** describes how to find document excerpts and turn them into an answer. A **PipelineVersion** saves a fixed configuration and its prepared inputs. **Test** and **Production** are **Deployments**, the stable endpoints that select which version answers a request. Building a version and making it live are separate actions.

**SupportBot** is an application calling Production. It has its own account, even when Alice creates it or asks a question through it. A **principal** is Inframeld's stable identity for a human or an application. Alice and SupportBot therefore have different principal IDs.

<a id="alice-and-supportbot-can-query-but-bob-cannot"></a>

### Alice and SupportBot can query, but Bob cannot

Assume authorized people have set up these permissions:

| Principal | Member of Support | Action permissions | Document-group membership |
| --- | --- | --- | --- |
| Alice, a human | Yes | Query on Production, Build on Support Pipeline | SupportKnowledge |
| SupportBot, an application | Yes | Query on Production | SupportKnowledge |
| Bob, a human | Yes | None yet | None yet |
| Carol, a human | Yes | Manage releases on Production | None yet |

After checking who is calling, Inframeld asks three separate questions:

1. **Do they currently belong to this project?** Being a member gets Bob into Support, but does not give him every permission there.
2. **May they perform this action on this resource?** SupportBot needs `Query` on Production. Permission to query Test would not cover Production.
3. **May they use these documents?** Their current group memberships determine which document excerpts may contribute to the answer.

The account must also be active, its session or key must be valid, and the operation's other requirements must hold. For example, the selected pipeline version must be ready to serve.

Alice and SupportBot can query Production using documents shared with SupportKnowledge. Bob cannot query it just because he belongs to Support. Carol can manage releases on Production without automatically gaining document access. Release operations that need protected inputs still check access to those inputs.

These permissions can change separately. Removing SupportBot's Query permission stops it querying Production, even if its key is valid. Removing its SupportKnowledge membership removes that document access, even if Query remains. Replacing a key changes neither permission.

> **Signing in proves who is calling. It does not grant project membership, action permissions, or document access.**

<a id="section-introduce-a-general-authorization-engine-or-policy-language-now"></a>

<a id="why-keep-permission-checks-in-access-and-postgresql"></a>

### Why keep permission checks in Access and PostgreSQL?

V1 has a fixed set of actions, direct permission assignments, and document groups. It does not need nested groups, custom roles, or rules that inherit through arbitrary relationships. PostgreSQL lets an access change and its related records succeed or fail together. Inframeld must still decide such things as whether a manager may leave or whether Alice may create a key for a powerful application.

OpenFGA could express these permissions, but would add a service and work to keep its state consistent with the application. PyCasbin would avoid that service, but still add a policy model, database integration, and synchronization between processes. Neither offered a demonstrated simplification for this design.

We therefore own the evaluator and its security tests. PostgreSQL does not supply the permission rules or prove that they will meet a particular workload. Reconsider an engine if the product needs deep inheritance, separate applications sharing permission rules, or measured performance improvements. More users or action names alone are not a reason to add one, and v1 needs no speculative engine adapter.

The rationale is recorded in [human authentication](../../../../docs/adr/ADR-0012-use-kratos-for-human-authentication.md) and [application-owned authorization](../../../../docs/adr/ADR-0013-keep-authorization-in-access-and-postgresql.md).

<a id="pipelines-and-releases"></a>

<a id="releases"></a> <a id="section-automatic-updates-do-not-grant-extra-permissions"></a> <a id="section-authorize-deployment-creation-and-initial-serving-together"></a>

<a id="7-pipelines-and-releases"></a>

## Pipelines and releases

Building prepares a version. Publishing makes it serve requests. Querying uses it. Permission for one of these actions does not grant the others, and a version being ready does not authorize anyone to publish it.

<a id="behavioral-scenarios"></a>

<a id="access-contract-review"></a>

<a id="reviewed-scenarios-and-remaining-116-work"></a>

### Behavioral scenarios

These examples record the design review, not executed tests or implemented guarantees:

| Scenario | Required outcome |
| --- | --- |
| Alice sends a cookie and bearer, or duplicate Authorization headers. | Reject before any provider call. No fallback even if credentials could identify the same human. |
| SupportBot sends a revoked key, or a verified key whose account/project is blocked. | Revoked credentials return 401. Verified but ineligible application/account/project state returns 403. Neither public key ID nor cached grants can admit it. |
| Bob can revoke a key but cannot grant SupportBot's HR actions. | Revocation remains allowed. Issuance fails its full current delegation/group checks. |
| An accepted case revision is edited or imported with an acceptance claim. | The changed/new revision is unreviewed until exact-revision review. Provenance does not supply authority. |
| The only manager is suspended and an operator repairs the group. | Suspend immediately. Repair only the reviewed stranded responsibility, giving the eligible replacement membership and management together. |

**Accepted scope:** fixed capability identifiers/targets/eligibility, seventeen Project creator grants and exact-resource creator assignments, human-only resource provisioning with application updates, case-audience administration/import defaults, single-use invitation rules and non-query diagnostic deferral. [The contract reference](actions-and-initial-grants.md) records application inputs/results, transport compatibility, maintenance intent and reviewed scenarios.

**Also settled by the final approval:** session fields and 5/10/15-second configurable starting budgets, safe authentication problem/challenge literals, new 32-KiB/100-assignment Access limits, exact-action grant listing, cookie/CSRF invitation admission, show-once key outcomes, the 64-KiB maintenance command and the 8-KiB private recovery callback boundary.

**Concrete draft now written:** [HTTP operations and bounded schemas](grant-contracts.md#http-operation-matrix), [host maintenance/proof](host-maintenance.md#maintenance-wire) and [private recovery handoff](private-recovery-handoff.md#recovery-wire). The older unchecked issue checklist is historical tracking, not proof that every consuming workflow is implemented. [The remaining-artifact table](#review-and-remaining-work) preserves downstream qualification and domain-schema ownership. These documentation changes do not edit or close issues.

Full domain schemas, pinned OSS provider compatibility and runtime/browser/CLI/OS qualification remain with their consuming specification and implementation/qualification issues. Historical cookie tests do not prove bearer, cross-provider recovery or application-key behavior. The [implemented boundary](credential-dispatch.md#implemented-human-authentication) records the newer bearer coverage and its mocked-provider limits. See [remaining contract work](#review-and-remaining-work).

<a id="review-and-remaining-work"></a>

## Behavioral scenarios

These are design-review scenarios, not executed tests:

| Scenario | Required outcome |
| --- | --- |
| SupportBot edits an existing Pipeline, then requests creation of another. | Permit the first with current Edit. Deny resource creation in v1, regardless of an imported definition. |
| Application import needs a missing Collection or a changed immutable profile. | Reject the known-ineligible plan before writes. Identify the human provisioning step, with no fallback identity. |
| Alice creates a Pipeline, loses the response and later loses an initial grant. | Recover the original result without recreating the removed grant or a second Pipeline. |
| SupportBot sends a valid key to an ordinary human-only create operation versus the human-session check. | The ordinary operation returns 403 for principal eligibility. The identity-specific session check returns 401 for unsupported family. |
| Alice removes a use-only grant and a later grant is assigned before replay. | Replay the original removal outcome. Do not remove the later assignment or encode absence as `canGrant: false`. |
| Alice creates a group with no stored document-action grant rows. | Her current manager relationship can administer its document-action assignments. She receives no automatic document-operation use. |
| Alice queries Project A's recipient directory with a target owned by Project B. | Reject the scope mismatch without exposing either directory. Exact-target authority cannot cross-bind Projects. |
| A different candidate or responsibility reuses the host operation ID. | Fail `idempotency_key_reused`. No grants or identity-link replacement. |

The session, grant command and cookie-only consent operations are implemented. Other routes and models remain unimplemented. Maintenance and private callback envelopes are design contracts. Production recovery still requires trusted original-flow evidence, durable admission, provider cleanup, reconciliation and release qualification. A passing local persistence test does not qualify those production boundaries.

<a id="maintainer-checks"></a> <a id="section-verify-the-security-boundaries-before-release"></a>

<a id="10-maintainer-checks"></a>

## Maintainer checks

For each feature, identify the caller, exact resource, required permission, and documents involved. Check current access when saving changes, sending protected content, and returning it. Every adapter must use Access. A login check or hidden Studio button is insufficient.

These are acceptance cases to verify, not a claim that the tests already pass:

| Try this | Expected result |
| --- | --- |
| Use a valid session or key without the required permission. | The operation is denied. Identity alone is insufficient. |
| Supply another user, group, issuer, delegated subject, project, or resource. | The caller cannot gain access by making the claim. Unsupported delegation and cross-project relationships are rejected. |
| Compare HTTP, supported MCP, and queued work. | They apply the same action and document rules. A queued job still needs current permission when it runs. |
| Revoke access after search but before sending or returning evidence. | Later protected use is denied. This includes historical evidence and sources the answer did not cite. |
| Remove and readmit a member, or replace a key. | Readmission does not restore removed grants. Key replacement preserves the application's identity and current permissions. |
| Compare a member with a manager. | Both read through ordinary membership. Only an eligible manager may change membership or appoint peers. Query and other action checks remain separate. |
| Remove management, then remove membership. | Demotion keeps reading access. Removing membership removes management too, and rejoining does not restore it. Another allowed group may still supply document access. |
| Remove a manager's membership while they try to add someone. | The backend checks their current membership and management during the project change. A request cannot use authority they have lost. |
| Inspect lists, configuration, and 404/403 responses. | Hidden resources and protected fields do not leak through metadata. |
| Lose a key-creation response or revoke the last key. | The secret cannot be retrieved by retrying. Emergency revocation does not require a replacement. |

Test behavior and database integrity against the supported deployment. Code-layout checks, library selection, and accepted ADRs are not evidence that security behavior or integrations work.

<a id="decision-and-reference-map"></a>

<a id="decision-map"></a>

<a id="11-decision-and-reference-map"></a>

## Decision and reference map

This guide explains current access behavior. The data model owns exact records and constraints. ADRs explain why the design was chosen and which alternatives were considered.
