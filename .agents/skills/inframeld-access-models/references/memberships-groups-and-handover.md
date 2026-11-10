# Memberships, groups and safe handover

<a id="memberships-groups-and-safe-handover"></a>

Alice brings Bob into Support, then prepares to leave. Joining a project does not grant an operation or document access. Explicit relationships let the application remove Alice without accidentally removing authority she gave Bob.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="membership-permissions-and-visibility"></a>

<a id="sharing"></a> <a id="section-bound-administration-grants-and-recovery"></a>

<a id="4-membership-permissions-and-visibility"></a>

## Membership, permissions, and visibility

Being responsible for a project does not mean being trusted with every document or action. Inframeld assigns specific responsibilities instead of providing an unrestricted in-app administrator role.

<a id="alice-brings-bob-into-support"></a>

### Alice brings Bob into Support

Bob has already been admitted to the installation. Alice uses `Manage project members` on Support to add him to the project. Bob can now see that project, but he still needs separate permissions to use its documents and Deployments.

Alice's permission covers membership in Support. It does not let her admit a new person to the installation, manage another project, or create application accounts. Those are separate actions. Removing Bob later clears his project access and follows the [handover rules](host-maintenance.md).

<a id="using-a-permission-and-sharing-it-are-different-responsibilities"></a>

### Using a permission and sharing it are different responsibilities

A **grant** is an assignment of one action to one recipient on one exact resource. It has two possible levels:

| Level | What the recipient may do |
| --- | --- |
| **Can use** | Perform the action on that resource. This is the default when sharing a permission. |
| **Can use and grant** | Perform the action, give it to others, or reduce or remove someone else's assignment of that same action on that resource. |

If Alice has `can use and grant` for Query on Production, she can let Bob query Production. Letting Bob pass that permission to others is a separate, explicit choice. Query on Production gives neither person permission to query Test.

The original person who assigned a permission does not own it forever. If Carol can grant Manage releases on Production, she can remove or downgrade Bob's assignment there even if Alice gave it to him. Carol still cannot change his other permissions without the relevant grant authority.

Applications receive **can use** only, for actions allowed to applications. Permission changes, manager appointments, user admission, and administration of incoming application accounts and keys require authorized humans.

<a id="group-managers"></a>

<a id="every-group-manager-is-also-a-member"></a>

### Every group manager is also a member

Membership supplies document access. Management adds the ability to add or remove eligible group members and appoint other managers. **Every manager must be an ordinary member of that same group.** An ordinary member cannot share access just because they can read.

For example, Alice is a member and manager of `SupportKnowledge`. She can read documents shared with it and add Bob as a member. Bob receives the same document access, but cannot add Carol. Either person still needs Query on Production to use those documents through Production. Alice cannot add anyone to `HRPrivate` unless she is also a member and manager there.

Managers are peers, with no owner above them. A current eligible manager may appoint another admitted human member of the project. Applications cannot be managers. Appointment gives the person both membership and management, keeping an existing membership if they already have one. The UI must explain that this includes access to **current and future documents shared with the group**.

| Change | What happens |
| --- | --- |
| Create a group | Its creator becomes its first member and manager. |
| Appoint a manager | Membership and management are saved together. |
| Remove management only | The person remains a member and keeps document access through the group. |
| Remove membership | Management is removed too. Rejoining later does not restore it. |

The backend saves these related changes together with their change number and audit record, as explained in [section 9](grant-administration.md#storing-access-and-handling-simultaneous-changes). A manager flag never substitutes for a missing membership when checking document access.

The last manager must appoint a replacement before deliberately leaving. Other changes must also preserve the required active managers and people who can grant permissions. [Emergency suspension](host-maintenance.md) is different because a compromised account must be blocked immediately.

Removing membership ends access through that group, but another allowed group may still provide access to the same document. Query, Build, Add documents, Update documents, and Delete documents remain separate permissions.

Creating a group requires the separate human project permission **Create access groups**. Creating `SupportTeam` gives Alice membership and management of that new group. It gives her no control over HRPrivate and moves no HR documents into SupportTeam.

[ADR-0049](../../../../docs/adr/ADR-0049-require-group-managers-to-be-ordinary-members.md) replaces the earlier rule that allowed managers without membership. The [data model](access-lifecycle-persistence.md#group-manager-membership-constraint) defines how the records enforce the current rule.

<a id="section-hide-inaccessible-resources"></a> <a id="section-limit-project-group-application-and-administration-visibility"></a>

<a id="bob-guesses-productions-id"></a>

### Bob guesses Production's ID

Assume Bob now has an action permission on Test, but none on Production. His list shows Test and omits Production. Asking directly for Production's ID returns the same safe **404** as a missing resource. Trying to publish to visible Test without Manage releases returns **403**. Both use the established [RFC 9457 error contract](../../inframeld-application-contracts/references/http-errors.md).

The following table shows what someone may see while their account, membership, and permissions remain valid:

| Information | Who may see it |
| --- | --- |
| Project Name, Display name and ID | Current project members. Installation permissions alone do not reveal every project. |
| Pipeline or Deployment name, ID, and basic availability | Someone with any effective action on that resource, at either grant level. |
| Resource configuration | Someone with View configuration or Edit configuration on that resource. |
| Group name and ID | Its members, managers, or people and applications with an action on it. Only managers may see who its members and managers are. |
| Application name and ID | A human with an administration action on it, or someone authorized to grant a permission who is choosing an eligible recipient. |
| Assigned actions and their grant levels | A human who may grant that exact action on that target. Humans may also inspect their own permissions. |
| Eligible recipients of a grant | Authorized project grantors see a limited directory containing stable ID, display name, and human/application kind. |
| Safe application-key metadata | A human with Issue or Revoke permission on that application. Delete alone is insufficient. |

Project metadata changes separately require human-only `edit-project-metadata`, current eligibility/membership and expected metadata revision. Membership administration supplies no rename authority. [The approved metadata contract](decision-project-metadata-authority.md) preserves original IDs, legacy labels and atomic stale/collision failure. Handover must preserve an eligible human grantor of this exact responsibility under the ordinary last-grantor rules. The implemented narrow host repair supplies only a stranded first grant, not broader membership management. Ordinary Project creation assigns this responsibility among its eighteen initial grants. Existing Projects receive no automatic backfill, and the human repair journey remains unqualified under #298.

These views do not expose document contents, unrelated grants, linked private resources, or saved secrets. Seeing a Deployment does not reveal its Pipeline. The recipient directory covers neither the whole installation nor a complete list of who has access to everything.

**Edit configuration includes viewing that configuration.** Removing View alone cannot hide it while Edit remains. Removing Edit leaves read-only access only if View remains. Giving someone Edit also gives them its included viewing ability, but managing a separate View assignment still requires authority to grant View. This is a fixed rule, not a configurable hierarchy of roles.

<a id="alice-leaves-after-granting-bob-access"></a>

### Alice leaves after granting Bob access

Bob keeps the permissions Alice gave him. The record of who granted them explains history, but does not make his access depend on Alice remaining. Removing Alice from Support clears **her** project grants, group memberships, and manager assignments. Adding her back later does not restore them.

For a resource that remains in use, ordinary departure, removal, or reduction of authority must leave an active eligible human able to grant each affected action. For example, if only Alice can grant Manage releases on Production, she must pass that authority to a replacement first. The replacement does not need every Production permission.

A person granting project or resource permissions must remain a project member. A person granting installation permissions must remain an admitted human. A group's last manager must appoint a replacement who is both a member and manager. Applications and suspended accounts do not count as replacements.

Two simultaneous departures must not each rely on the other person staying. [Section 9](grant-administration.md#storing-access-and-handling-simultaneous-changes) explains how the backend prevents that.

<a id="alice-is-compromised-while-she-is-the-last-manager"></a>

### Alice is compromised while she is the last manager

Suspend Alice immediately, even if that leaves no active group manager or person able to grant an action. Suspension preserves her memberships, manager assignments, and action permissions but blocks their use, including reading and administration. Other authorized people keep their access, although some administrative work may now be impossible.

Prefer recovering Alice's **existing legitimate account**, keeping the same local principal. Verify her identity, replace compromised sign-in methods, invalidate old sessions, and review suspicious permission and key changes. An authorized person must then deliberately lift the suspension. A password reset alone does not do this, and permissions explicitly removed during the incident stay removed.

Kratos handles recovery of the sign-in identity. Access decides whether the recovered account may act. This integration still needs implementation and testing.

<a id="admission-memberships-and-lifecycle"></a>

<a id="inspect-and-administer-access-groups"></a>

## Inspect and administer access groups

The native group creation, member/manager changes, exact metadata reads and unused-group deletion are implemented. [The task guide](../../../../apps/docs/src/app/guides/manage-access-groups/page.mdx) owns copyable HTTP and generated-client examples. [Lifecycle persistence](access-lifecycle-persistence.md#group-administration-and-deletion-recovery) owns atomic effects, original results and the deletion boundary.

An eligible current Project principal may inspect one exact group ID or resolve its exact Name only when it is an ordinary member, manager or holder of an exact supported Add, Update or Delete documents grant on that group. Unsupported stored action identifiers confer no visibility. This gives safe IDs, nullable legacy Name, Display name, creation time and current Project Access revision. It gives no Project-wide group directory or document inventory. Hidden, absent and retired names return the safe not-found result. The inspected HTTP metadata routes accept supported human credentials and configured application keys through [ordinary credential dispatch](credential-dispatch.md#select-one-credential-before-verification). Application callers receive [current key and account checks](application-keys.md#application-key-current-authorization) before disclosure. Public key issuance and a mounted MCP server remain separate delivery work.

Only current eligible human managers list the group's safe principal IDs, kinds and Display names. Each request rechecks management. Pages use ascending principal UUIDs, default 25 and maximum 100, and an opaque cursor bound to installation, Organization, Project, group, collection and position. A members cursor cannot select managers or another group. Reads change neither audit nor revision.

Creation requires current Project `create-access-groups` use authority and a reviewed Project revision. PUT uses strict revision JSON and returns 201 for a changed assignment or 200 for an original no-op. DELETE carries exactly one revision query value and no body, and returns 200. Current authority precedes original replay. Saved receipts describe original outcomes rather than restoring a later removed relationship.

The current deletion writer handles actual Access relationships, including restrictive [saved upload-default references](upload-default-contracts.md#persistence-and-admission-boundaries). An in-use default group returns 409 and rolls back deletion until an authorized replacement removes the reference. Future Document/source/active-upload/case owners add their real restrictive references and compatible coordination. Their absence does not create a replacement reference registry or qualify those future journeys.

### Admission, memberships and lifecycle

In the following table, `revision` means the required `expectedAccessRevision` field, and `names` means required `name` and `displayName`. All rows use Human administration unless stated otherwise. The single installation's Organization ID is explicit, not an implicit superadministrator scope. A body revision always refers to the coordinated Organization or Project access revision, not a credential or resource content revision.

| Method and route | Operation ID | Request / result | Authority and success |
| --- | --- | --- | --- |
| `POST /v1/organizations/{organization_id}/human-admissions` | `admitHuman` | `HumanAdmissionRequest`: `identityId`, `expectedAccessRevision`. `HumanAdmissionResponse`: mutation fields, `organizationId`, `principalId`, `changed` | `admit-users`. Verify current configured Kratos identity and unique authority/subject link. 201 new admission, 200 already-admitted no change. Never restore a blocked principal. |
| `POST /v1/organizations/{organization_id}/humans/{principal_id}/suspend` | `suspendHuman` | `HumanSuspensionRequest`: revision, `reason`. `HumanSuspensionResponse`: mutation fields, organization/principal IDs, `accessBlocked: true`, `cleanupOperationId` | `suspend-users`. 202 after immediate suspension/block plus original durable cleanup obligation commit. No handover prerequisite. |
| `POST /v1/organizations/{organization_id}/humans/{principal_id}/restore` | `restoreHuman` | `HumanRestorationRequest`: revision, `securityReviewReference`. `HumanRestorationResponse`: mutation fields, organization/principal IDs | `restore-users`. 200 only after current stable Kratos identity, same legitimate principal, required confirmed cleanup, security review and no pending newer block. Does not recreate relationships. |
| `POST /v1/projects` | `createProject` | `ProjectCreationRequest`: `organizationId`, `name`, `displayName`, `expectedAccessRevision` of the Organization. `ProjectCreationResponse`: original operation fields, Organization/Project IDs, names, Project `accessRevision: 1`, `metadataRevision: 0` and fixed eighteen `initialGrants` | Implemented eligible-human operation requiring Organization `create-projects`. 201. Save creator membership/grants/audit/result together. Organization revision stays unchanged. Starter provisioning remains separate. |
| `PUT /v1/projects/{project_id}/members/{principal_id}` | `addProjectMember` | `ProjectMembershipRequest`: revision. `ProjectMembershipResponse`: mutation fields, project/principal IDs, `member: true`, `changed` | `manage-project-members`. Admitted eligible human recipient only. 201 added or 200 unchanged. Application membership comes from account creation. |
| `DELETE /v1/projects/{project_id}/members/{principal_id}` | `removeProjectMember` | Revision query / `ProjectMembershipRemovalResponse`: mutation fields, IDs, `removed: true`, `changed` | `manage-project-members`. 200. Ordinary handover, remove that human's project grants/groups/managers together. Application retirement is separate. |
| `POST /v1/projects/{project_id}/access-groups` | `createAccessGroup` | `AccessGroupCreationRequest`: names, revision. `AccessGroupCreationResponse`: mutation fields, `projectId`, `accessGroupId`, names, `creatorPrincipalId` | `create-access-groups`. 201 with creator membership/management together, no extra document grants. |
| `PUT` / `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}/members/{principal_id}` | `addAccessGroupMember` / `removeAccessGroupMember` | `AccessGroupMembershipRequest`: revision (PUT) or revision query (DELETE). `AccessGroupMembershipResponse` / `AccessGroupMembershipRemovalResponse`: mutation fields, project/group/principal IDs, `member: true` or `removed: true`, `changed` | Current group manager. Admitted current project human/application recipient. PUT 201/200, DELETE 200. Removal removes management too under handover. |
| `PUT` / `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}/managers/{principal_id}` | `appointAccessGroupManager` / `removeAccessGroupManager` | `AccessGroupManagerRequest`: revision (PUT) or revision query (DELETE). `AccessGroupManagerResponse` / `AccessGroupManagerRemovalResponse`: mutation fields, IDs, `manager: true` or `removed: true`, `changed` | Current group manager. Eligible human recipient only. Appointment explicitly saves membership. PUT 201/200, DELETE 200. Demotion retains membership. Preserve last eligible manager. |
| `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}` | `deleteAccessGroup` | Revision query / `AccessGroupDeletionResponse`: mutation fields, IDs, `removed: true` | Current group manager. 200 only if unused under all stored document/source/upload/default/case references. Otherwise 409. |
| `POST /v1/projects/{project_id}/application-accounts` | `createApplicationAccount` | `ApplicationAccountCreationRequest`: names, revision. `ApplicationAccountCreationResponse`: mutation fields, `projectId`, `principalId`, names, fixed three human `initialGrants` | `create-application-accounts`. 201. Application starts with no actions, groups or key. Account identity is its shared principal ID, not a second account UUID. |
| `GET /v1/projects/{project_id}/application-accounts/{application_principal_id}` | `getApplicationAccount` | `ApplicationAccountMetadataResponse`: safe principal/Project IDs, nullable legacy Name, Display name, status, creation time and current Access revision | Any exact human account-administration action. 200. No key or grant inventory. |
| `GET /v1/projects/{project_id}/application-accounts/resolve?name=<exact-name>` | `resolveApplicationAccount` | Same safe metadata, resolved only by the exact Project-scoped Name | Same current authority as ID inspection. Hidden or retired Name returns safe 404, without redirect or Project-wide inventory. |
| `DELETE /v1/projects/{project_id}/application-accounts/{application_principal_id}` | `deleteApplicationAccount` | Revision query / `ApplicationAccountDeletionResponse`: mutation fields, project/application principal IDs, `accessBlocked: true`, optional `cleanupOperationId` | Exact `delete-application-account`. 200 if local retirement/key revocation complete, 202 if durable cleanup remains. Preserve project-owned work. |
| `DELETE /v1/projects/{project_id}` | `deleteProject` | Revision query / owning deletion outcome | Exact `delete-project` plus current human/project membership. 202 on new admission. See semantic handoff below rather than selecting a new job schema. |
| `GET /v1/projects/{project_id}/my-access` | `getMyProjectAccess` | No body / `MyProjectAccessResponse`: `projectId`, `principalId`, `accessRevision`, bounded `grants`, `groupMemberships`, `groupManagements`, `nextCursor` | Own human access. Current project member, actual caller only. 200. No other principal's assignments or hidden linked resources. |
| `GET /v1/my-organization-access` | `getMyOrganizationAccess` | No body / `MyOrganizationAccessResponse`: `organizationId`, `principalId`, `accessRevision`, Organization `grants` | Implemented own human access. 200 for the actual admitted eligible human, including `grants: []`. No installation inventory or caller-selected principal. |

`securityReviewReference` is a safe audit reference supplied by the authorized human who performed the legitimate-identity/security review. It is not proof by itself, a new automated review service or a way to change the identity link. The service checks current configured Kratos identity against the stable link and all required original cleanup obligations. Restoration remains the deliberate responsibility described in [Access](recovery.md#deliberate-restoration-cutover). The accepted [ADR-0127](../../../../docs/adr/ADR-0127-fence-human-authentication-evidence-at-restoration.md) transition advances the existing identity version exactly once with state, revision, audit and immutable original outcome. Replay and non-transitions advance nothing. Bound browser evidence and linked-human consent checks must honor that cutover before protected work. The [explicit late-session limit](browser-sessions.md#restoration-evidence-cutover) is accepted, not a universal provider fence. The suspension/restoration rows remain accepted transport contracts with implementation and qualification unfinished, not delivered endpoints. No new request/response field is selected by this extension.

The application create and metadata GET rows are implemented through [the account workflow](application-keys.md#implemented-application-account-creation). Safe key GET rows follow [the key-metadata contract](application-key-contracts.md#application-key-metadata-reads). Account deletion remains unfinished under #233. Human procedure preparation and acceptance for the new account journey remain tracked by [#352](https://github.com/matejpalenik/inframeld/issues/352).

<a id="read-stored-project-members"></a>

### Read stored Project members

`GET /v1/projects/{project_id}/members` (`listProjectMembers`) is implemented as a bounded, human-only read. Require current human eligibility, Project visibility/membership and **use** of `manage-project-members`, not permission to grant it. A currently eligible creator can inspect the real membership and action assigned by ordinary Project creation. No second admitted account is needed for that case.

The page contains `projectId`, the current Project `accessRevision`, `items` and `nextCursor`. Each item contains only `principalId`, `displayName` and human/application `kind`. Preserve stored inactive memberships rather than filtering them into a list of eligible actors. Presence proves neither current eligibility nor an action grant. Return no emails, grants, group relationships or totals. Reading changes no membership or revision.

The default limit is 25, with 1–100 accepted. Apply exact scope before resuming after the principal UUID and fetching at most `limit + 1` rows. Return at most `limit` items and a cursor only when more rows exist. A left lateral join retains current authorization/revision facts when continuation is empty. The [service](../../../../apps/backend/src/inframeld_backend/access/application/services/project_members_service.py) uses that coherent observation before disclosing the page.

Pass the opaque cursor unchanged. Its endpoint/version/order and installation/Organization/Project scope are checked, but it is not a signature, expiry or permission token. Reject malformed/incompatible cursors and duplicate/unknown query fields or a GET body with the safe `422` problem. Recheck current credentials, eligibility, visibility and exact use authority for every page. The revision describes that page, not a frozen traversal. Permission loss is a failure, never an empty success.

[The task guide](../../../../apps/docs/src/app/guides/list-project-members/page.mdx) gives HTTP and generated-client examples with existing credential setup. [Human qualification #319](https://github.com/matejpalenik/inframeld/issues/319) remains unready. Controlled fixture rows are not a human setup recipe or evidence of human pagination and handover.

<a id="change-project-membership"></a>

### Change Project membership

The registered `addProjectMember` and `removeProjectMember` routes implement the Project membership rows above. Both require a currently eligible human with Project membership and **use** of `manage-project-members`. Grant authority is unnecessary. Ordinary admission is a separate prerequisite for adding Bob. Removal may clear an inactive or recovery-blocked human without restoring the account first. An application recipient uses its separate account lifecycle.

Review the Project `accessRevision` returned by the member list. PUT sends exactly `{"expectedAccessRevision": revision}` as bounded JSON. DELETE sends exactly one `expectedAccessRevision` query field and no body. Both carry the original single `Idempotency-Key`. A changed add returns 201, an already-present add returns 200, and removal returns 200 whether changed or already absent. Each typed response includes `operationId`, `idempotencyExpiresAt`, `projectId`, `principalId`, `accessRevision` and `changed`, plus `member: true` or `removed: true`. All responses use `Cache-Control: no-store`.

For new work, the service checks the reviewed revision after obtaining the Organization then Project coordination turn. Adding creates bare membership only. Removing checks each affected exact-action grantor and group-manager responsibility, then removes only the departing recipient's scoped relationships. A replacement must be an active eligible human, a current Project member and coherently linked to its identity, without a pending recovery block. A group manager must also be an ordinary group member. The manager alternative can preserve that group's Add/Update/Delete document authority, never unrelated Project or application-account authority. Missing responsibility returns 409 with no partial cleanup. There is no automatic delegation or replacement.

Current credential and action checks run before completed replay. A retry with the same complete request returns the original status, revision, expiry and change flag. It does not restore a removed membership or remove a later rejoin. A fresh stale revision, changed meaning under the same key, ineligible add recipient or unsafe departure fails atomically. Self-departure is subject to the same rules and ends the caller's Project visibility, including authority to recover its earlier response afterward.

The [service](../../../../apps/backend/src/inframeld_backend/access/application/services/project_membership_change_service.py), [receipt storage](access-lifecycle-persistence.md#project-membership-original-results) and [user guide](../../../../apps/docs/src/app/guides/manage-project-members/page.mdx) describe the implementation. Public grant administration remains separate. Group membership and manager changes use the implemented group workflow above. Their absence does not disable the automatic departure guard. Human setup, procedure preparation and acceptance remain deferred under #319.

The group's `/members` (`listAccessGroupMembers`) and `/managers` (`listAccessGroupManagers`) require current group management. Return the existing bounded page of safe `principalId`, `displayName`, `kind`, ordered by principal UUID, with the exact scope bound into the cursor. They do not expose other memberships or document contents. Own Project access uses one combined page of at most `limit` entries across its three arrays, ordered by relationship kind then target UUID then action literal, and a scope/principal-bound cursor. A grant item contains typed `target`, `actionId`, `canGrant`. Membership/management items contain only `accessGroupId`. Return only stored assignments and actual relationships, not fabricated implied grant rows. `nextCursor` is a string or null. Organization own-access lists only its four supported stored action assignments. A page reports a current access revision for that read. It is not a permission snapshot for later execution.

<a id="alice-wants-to-share-an-hr-handbook-with-support"></a>

### Alice wants to share an HR handbook with Support

The handbook currently allows HRPrivate. Alice manages SupportKnowledge but not HRPrivate. She cannot add SupportKnowledge to its audience just because she manages the destination group.

Changing the audience requires **one authorized human who manages every group in the current or proposed allowlist**. This includes groups being added, removed, or retained. Changing `HRPrivate + SupportKnowledge` to only `SupportKnowledge` still requires management of both groups. Otherwise Alice could bypass HR's protection by removing HRPrivate first.

Reading or updating the document is not enough. V1 uses one person trusted to manage all affected groups, without adding document owners or a multi-person approval process. The backend checks the saved audience and current manager assignments when saving the change. The resulting policy applies to every version of the Document.
