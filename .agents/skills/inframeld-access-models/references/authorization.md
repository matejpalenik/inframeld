# Current permissions and bounded administration

Alice and SupportBot both belong to Support, but only SupportBot has Query on Production. Alice's membership does not supply that missing grant. Carol can manage releases without automatically reading every document. Access keeps these relationships separate so administration does not become an implicit data-reading bypass.

## Concepts and owners

A product operation asks whether the principal is eligible now, belongs to the project, may perform the exact action on the target and may read any required documents. Default to denial. Groups or permissions supplied by the caller cannot establish authority.

A grant records an action that a recipient may perform on a target. It can permit use or use-and-grant. The latter allows delegation, which means giving that exact action on that exact target to someone else. Applications may receive eligible use grants, never human-only administration or delegation.

The shared schema stores current grants in target-specific tables, with one recipient/action/target assignment and a `can_grant` value. Audit history is separate from these current assignments.

Group membership supplies document reading through an explicit allowlist. Management supplies sharing authority. Managers are peers, with no privileged owner above them. Every manager must also have ordinary membership in the same group.

Appointing a manager records both relationships. Demotion removes management while keeping membership. Removing membership also removes management in the same transaction. Rejoining does not restore management automatically. Action grants have their separate lifecycle.

## Follow a grant change

1. Authenticate before the write transaction. The Access service loads current facts in the caller's transaction under the accepted organization/project lock protocol.
2. Interpret authentication evidence before visibility or replay. Reject a stored principal-kind mismatch as an internal contract error. Reject stale human OAuth evidence with the generic invalid-token outcome.
3. Apply project visibility before disclosing authority or recipient existence. Hidden projects remain 404. For visible projects, missing eligibility, recovery restrictions or authority produce the documented denial. Check the actor before revealing an absent recipient.
4. Require an eligible human grantor with exact delegation authority. The complete grant service also checks returned project scope against the unchanged Command before idempotency reservation or replay. A mismatch is an internal runtime failure that rolls back and receives the generic HTTP 500.
5. For new work, load the recipient's membership in checked scope and verify organization, project and recipient. Invoke `ProjectMembership.assign_use_only_grant()`, save with the checked project-wide revision and original operation ID, then commit required audit and completion together.

The shared eligibility policy owns common account/recovery decisions. Operation policies add their own requirements. Access services own current reads and failure ordering. Target-specific persistence does not create separate policy implementations.

Facts readers can compose efficient SQL expressions, but must not instantiate another executing reader merely to fill a facts field. Grant, scope-revision and account-status mutations all follow the accepted lock protocol. Application-owned grant transactions and caller-bound admission helpers retain distinct transaction ownership.

## Typed authorization capabilities

`Authorizer[RequestType, ResultType]` defines abstract `require_authorization(access, request)`. `ActionAuthorizer` and `ProjectGrantAuthorizer` specialize that contract and inherit the required method. Concrete implementations and test doubles explicitly inherit their family and provide compatible implementations.

Access owns the authorization request DTOs. They are separate from business Commands and retry metadata. Trusted application workflows select the required actions. Reuse a permission family across operations, adding a family only when its decision inputs or rules materially differ.

Signature compatibility does not prove that authorization happens before protected disclosure, reservation or replay. Verify that ordering with behavioral tests. [Protocol conventions](../../inframeld-coding-standards/references/protocols-and-persistence.md) explain abstract methods, overrides and typing checks.

## Aggregate and persistence boundary

`ProjectMembership` owns one recipient's direct project grants. Its identity is project plus principal. Immutable `ProjectActionGrant` children identify project, recipient and action. The aggregate rejects duplicate assignment at either level and application delegation. The supported workflow adds attributed use-only grants without replacing historical values.

Its specific repository loads existing membership only. It neither provisions membership nor authorizes, commits, acquires locks or retries. Save additions with one conditional project-wide revision increment and required audit. Membership creation, revocation and cross-member lifecycle operations remain deferred.

Loaded objects and their immutable snapshots belong to one active transaction. Bind the exact instances to that transaction. Preserve timestamps and attribution, and compare child values independently of entity identity. Discard the instances after the transaction ends or a save fails so a later attempt starts from current state.

## Administration and document audiences

Do not infer permission from a title, creator history, installation administration or membership. Fixed creator assignments are explicit grants, not permanent authority. The accepted catalogue defines seventeen initial additional-Project actions, thirteen Pipeline actions and seven Deployment actions. The historical eleven-action seed is superseded. Existing resources receive no automatic backfill.

An audience is the set of groups permitted to read protected material. Document audiences, source/imported-case audiences and upload defaults need deliberate authorized destination groups. Imported metadata and upstream access-control lists cannot grant access.

Query on a Pipeline uses its working settings, while Query on a Deployment uses serving selection. Neither grants the other. Query-trace inspection requires its own grant on the exact resource and current source access, including other callers' answers. There is no Experiment resource.

After successful Query authorization, an empty permitted source set takes the ordinary no-evidence path without Chroma search. A forbidden query, an empty saved document allowlist or lost permission to a protected evidence bundle still denies the relevant operation. Never disguise denial as a successful empty read.

## Traces, feedback and evaluation evidence

Trace inspection can be explicitly granted to eligible humans or applications, with current source checks. Project tracing/retention changes are human-only, and explicit history deletion needs separate human deletion authority. Query, inspection and policy management are different grants. Recording does not depend on the caller's inspection rights.

Imports can preserve destination policy, but restricted explicit apply must be denied without identity fallback. Automatic expiry and source erasure do not need new human approval for each record. These query-inspection rules grant no unspecified non-query history access.

CLI feedback includes authorized reports and correction of the originating principal's own live-answer rating. Reports do not authorize changing someone else's rating. Current evidence checks filter totals as well as comments.

Evaluation has six exact-Pipeline use permissions for eligible humans and applications. Human case-audience administration and fixed creator assignments remain separate. Generated cases inherit source protections. Check current access before sending data to a model and again before later disclosure.

Ragas receives no credentials or independent provider clients. Generator/judge bindings may reuse authorized connections without another key, but never imply a model/provider fallback.

## Departure, invitations and host maintenance

Ordinary departure preserves required management. Emergency suspension immediately blocks even a sole manager while preserving relationship records. Scoped operator recovery explicitly assigns membership and management to an eligible replacement without reviving the compromised account or granting unrestricted reading. Each project, resource, document, group and application-account deletion has separate permissions and reference rules.

Invitation admission rechecks verified identity and current issuer authority for its exact assignments.

Host maintenance supplies its own narrow authority. The version 1 maintenance draft uses a transient Hydra human token only for independent candidate-identity checks. Host execution authorizes the operation. Ordinary login cannot become host authority. Keep session budgets, mutation limits, invitation, grant-listing, private recovery and maintenance inputs under their exact contracts.

## Status and sources

Access policy remains application-owned in PostgreSQL. OpenFGA and PyCasbin were considered but not selected. Follow the [recorded reconsideration criteria](../../../../docs/development/access-control.md#section-introduce-a-general-authorization-engine-or-policy-language-now) before proposing a generic policy language, speculative adapter or authorization cache.

The 14-table foundation enforces selected scoped relationships, manager membership, resource/principal kinds, uniqueness and application use-only grants. The action catalogue is not yet enforced by database checks. Grant tables for future resource kinds do not authorize implementing those domains now. Most administration, audit-retention and physical/wire workflows still need implementation or qualification.

The reviewed catalogue and assignments were accepted on 2026-10-04. The [Access contract review](https://github.com/matejpalenik/inframeld/issues/116) is closed as historical tracking. That does not make downstream HTTP schemas, maintenance/recovery drafts or runtime qualification complete.

The supported use-only human project grant is the complete reference workflow. Both grant-facts and linked recovery-admission adapters use fixed five-second database deadlines including lock waits, leaving rollback to the caller. The [typed authorization capabilities](#typed-authorization-capabilities) above and the [transaction/service chain](../../inframeld-application-contracts/references/transactions-jobs-and-idempotency.md) explain the shared contracts. Type conformance alone cannot prove ordering before disclosure or mutation.

- [Access control](../../../../docs/development/access-control.md), [bounded administration](../../../../docs/development/access-control.md#section-bound-administration-grants-and-recovery), [shared eligibility](../../../../docs/development/access-control.md#shared-principal-eligibility), [group managers](../../../../docs/development/access-control.md#group-managers), [query authority](../../../../docs/development/access-control.md#pipeline-query-authority) and [maintainer checks](../../../../docs/development/access-control.md#maintainer-checks).
- [Trace authority](../../../../docs/development/access-control.md#trace-authority), [trace lifecycle](../../../../docs/development/observability.md), [feedback authority](../../../../docs/development/answer-feedback.md#authorization), [Evaluation permissions](../../../../docs/development/evaluation.md#operation-authority), [case audiences](../../../../docs/development/evaluation.md#case-audiences) and [non-query diagnostic deferral](../../../../docs/development/observability.md#non-query-diagnostics).
- [Access contracts](../../../../docs/development/access-contracts.md), [catalogue and assignments](../../../../docs/development/access-contracts.md#initial-assignments), [invitations](../../../../docs/development/access-contracts.md#invitations), [maintenance](../../../../docs/development/access-contracts.md#maintenance) and [remaining work](../../../../docs/development/access-contracts.md#review-and-remaining-work) preserve the accepted review's scope and closed historical tracking status without claiming downstream completion.
- [Access records](../../../../docs/development/data-model.md#access), [manager constraint](../../../../docs/development/data-model.md#group-manager-membership-constraint), [write coordination](../../../../docs/development/access-control.md#section-accepted-write-coordination-and-proposed-indexes), [grant chain](../../../../docs/development/application-structure.md#grant-command-flow) and [membership repository](../../../../docs/development/application-structure.md#membership-aggregate-and-repository).
- Rationale: [application-owned policy](../../../../docs/adr/ADR-0013-keep-authorization-in-access-and-postgresql.md), [bounded delegation](../../../../docs/adr/ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [document groups](../../../../docs/adr/ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [emergency recovery](../../../../docs/adr/ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [manager membership](../../../../docs/adr/ADR-0049-require-group-managers-to-be-ordinary-members.md), [creator grants](../../../../docs/adr/ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md), [shared eligibility](../../../../docs/adr/ADR-0064-centralize-principal-eligibility-and-keep-access-aggregates-focused.md) and [membership aggregate](../../../../docs/adr/ADR-0068-model-project-grants-through-project-membership-aggregates.md).
