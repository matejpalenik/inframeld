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
| Project name and ID | Current project members. Installation permissions alone do not reveal every project. |
| Pipeline or Deployment name, ID, and basic availability | Someone with any effective action on that resource, at either grant level. |
| Resource configuration | Someone with View configuration or Edit configuration on that resource. |
| Group name and ID | Its members, managers, or people and applications with an action on it. Only managers may see who its members and managers are. |
| Application name and ID | A human with an administration action on it, or someone authorized to grant a permission who is choosing an eligible recipient. |
| Assigned actions and their grant levels | A human who may grant that exact action on that target. Humans may also inspect their own permissions. |
| Eligible recipients of a grant | Authorized project grantors see a limited directory containing stable ID, display name, and human/application kind. |
| Safe application-key metadata | A human with Issue or Revoke permission on that application. Delete alone is insufficient. |

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

### Admission, memberships and lifecycle

In the following table, `revision` means the required `expectedAccessRevision` field, and `names` means required `name` and `displayName`. All rows use Human administration unless stated otherwise. The single installation's Organization ID is explicit, not an implicit superadministrator scope. A body revision always refers to the coordinated Organization or Project access revision, not a credential or resource content revision.

| Method and route | Operation ID | Request / result | Authority and success |
| --- | --- | --- | --- |
| `POST /v1/organizations/{organization_id}/human-admissions` | `admitHuman` | `HumanAdmissionRequest`: `identityId`, `expectedAccessRevision`. `HumanAdmissionResponse`: mutation fields, `organizationId`, `principalId`, `changed` | `admit-users`. Verify current configured Kratos identity and unique authority/subject link. 201 new admission, 200 already-admitted no change. Never restore a blocked principal. |
| `POST /v1/organizations/{organization_id}/humans/{principal_id}/suspend` | `suspendHuman` | `HumanSuspensionRequest`: revision, `reason`. `HumanSuspensionResponse`: mutation fields, organization/principal IDs, `accessBlocked: true`, `cleanupOperationId` | `suspend-users`. 202 after immediate suspension/block plus original durable cleanup obligation commit. No handover prerequisite. |
| `POST /v1/organizations/{organization_id}/humans/{principal_id}/restore` | `restoreHuman` | `HumanRestorationRequest`: revision, `securityReviewReference`. `HumanRestorationResponse`: mutation fields, organization/principal IDs | `restore-users`. 200 only after current stable Kratos identity, same legitimate principal, required confirmed cleanup, security review and no pending newer block. Does not recreate relationships. |
| `POST /v1/projects` | `createProject` | `ProjectCreationRequest`: `organizationId`, `name`, `displayName`, revision. `ProjectCreationResponse`: mutation fields, `projectId`, names and fixed seventeen `initialGrants` | Organization `create-projects`. 201. Save creator membership/grants/audit/result together. Starter provisioning remains's separate workflow. |
| `PUT /v1/projects/{project_id}/members/{principal_id}` | `addProjectMember` | `ProjectMembershipRequest`: revision. `ProjectMembershipResponse`: mutation fields, project/principal IDs, `member: true`, `changed` | `manage-project-members`. Admitted eligible human recipient only. 201 added or 200 unchanged. Application membership comes from account creation. |
| `DELETE /v1/projects/{project_id}/members/{principal_id}` | `removeProjectMember` | Revision query / `ProjectMembershipRemovalResponse`: mutation fields, IDs, `removed: true`, `changed` | `manage-project-members`. 200. Ordinary handover, remove that human's project grants/groups/managers together. Application retirement is separate. |
| `POST /v1/projects/{project_id}/access-groups` | `createAccessGroup` | `AccessGroupCreationRequest`: names, revision. `AccessGroupCreationResponse`: mutation fields, `projectId`, `accessGroupId`, names, `creatorPrincipalId` | `create-access-groups`. 201 with creator membership/management together, no extra document grants. |
| `PUT` / `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}/members/{principal_id}` | `addAccessGroupMember` / `removeAccessGroupMember` | `AccessGroupMembershipRequest`: revision (PUT) or revision query (DELETE). `AccessGroupMembershipResponse` / `AccessGroupMembershipRemovalResponse`: mutation fields, project/group/principal IDs, `member: true` or `removed: true`, `changed` | Current group manager. Admitted current project human/application recipient. PUT 201/200, DELETE 200. Removal removes management too under handover. |
| `PUT` / `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}/managers/{principal_id}` | `appointAccessGroupManager` / `removeAccessGroupManager` | `AccessGroupManagerRequest`: revision (PUT) or revision query (DELETE). `AccessGroupManagerResponse` / `AccessGroupManagerRemovalResponse`: mutation fields, IDs, `manager: true` or `removed: true`, `changed` | Current group manager. Eligible human recipient only. Appointment explicitly saves membership. PUT 201/200, DELETE 200. Demotion retains membership. Preserve last eligible manager. |
| `DELETE /v1/projects/{project_id}/access-groups/{access_group_id}` | `deleteAccessGroup` | Revision query / `AccessGroupDeletionResponse`: mutation fields, IDs, `removed: true` | Current group manager. 200 only if unused under all stored document/source/upload/default/case references. Otherwise 409. |
| `POST /v1/projects/{project_id}/application-accounts` | `createApplicationAccount` | `ApplicationAccountCreationRequest`: names, revision. `ApplicationAccountCreationResponse`: mutation fields, `projectId`, `principalId`, names, fixed three human `initialGrants` | `create-application-accounts`. 201. Application starts with no actions, groups or key. Account identity is its shared principal ID, not a second account UUID. |
| `DELETE /v1/projects/{project_id}/application-accounts/{application_principal_id}` | `deleteApplicationAccount` | Revision query / `ApplicationAccountDeletionResponse`: mutation fields, project/application principal IDs, `accessBlocked: true`, optional `cleanupOperationId` | Exact `delete-application-account`. 200 if local retirement/key revocation complete, 202 if durable cleanup remains. Preserve project-owned work. |
| `DELETE /v1/projects/{project_id}` | `deleteProject` | Revision query / owning deletion outcome | Exact `delete-project` plus current human/project membership. 202 on new admission. See semantic handoff below rather than selecting a new job schema. |
| `GET /v1/projects/{project_id}/my-access` | `getMyProjectAccess` | No body / `MyProjectAccessResponse`: `projectId`, `principalId`, `accessRevision`, bounded `grants`, `groupMemberships`, `groupManagements`, `nextCursor` | Own human access. Current project member, actual caller only. 200. No other principal's assignments or hidden linked resources. |
| `GET /v1/my-organization-access` | `getMyOrganizationAccess` | No body / `MyOrganizationAccessResponse`: `organizationId`, `principalId`, `accessRevision`, Organization `grants` | Own human access. 200 for actual admitted human only. No installation inventory. |

`securityReviewReference` is a safe audit reference supplied by the authorized human who performed the legitimate-identity/security review. It is not proof by itself, a new automated review service or a way to change the identity link. The service checks current configured Kratos identity against the stable link and all required original cleanup obligations. Restoration remains the deliberate responsibility described in [Access](recovery.md#identity-recovery-cleanup).

`GET /v1/projects/{project_id}/members` (`listProjectMembers`) requires `manage-project-members`. The group's `/members` (`listAccessGroupMembers`) and `/managers` (`listAccessGroupManagers`) require current group management. Return the existing bounded page of safe `principalId`, `displayName`, `kind`, ordered by principal UUID, with the exact scope bound into the cursor. They do not expose other memberships or document contents. Own Project access uses one combined page of at most `limit` entries across its three arrays, ordered by relationship kind then target UUID then action literal, and a scope/principal-bound cursor. A grant item contains typed `target`, `actionId`, `canGrant`. Membership/management items contain only `accessGroupId`. Return only stored assignments and actual relationships, not fabricated implied grant rows. `nextCursor` is a string or null. Organization own-access lists only its four supported stored action assignments. A page reports a current access revision for that read. It is not a permission snapshot for later execution.

<a id="alice-wants-to-share-an-hr-handbook-with-support"></a>

### Alice wants to share an HR handbook with Support

The handbook currently allows HRPrivate. Alice manages SupportKnowledge but not HRPrivate. She cannot add SupportKnowledge to its audience just because she manages the destination group.

Changing the audience requires **one authorized human who manages every group in the current or proposed allowlist**. This includes groups being added, removed, or retained. Changing `HRPrivate + SupportKnowledge` to only `SupportKnowledge` still requires management of both groups. Otherwise Alice could bypass HR's protection by removing HRPrivate first.

Reading or updating the document is not enough. V1 uses one person trusted to manage all affected groups, without adding document owners or a multi-person approval process. The backend checks the saved audience and current manager assignments when saving the change. The resulting policy applies to every version of the Document.
