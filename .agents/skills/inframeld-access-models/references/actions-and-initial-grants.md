# Actions and explicit initial grants

<a id="actions-and-explicit-initial-grants"></a>

Alice creates Support and grants SupportBot one operation on Production. Membership, document reading and permission to delegate remain separate. The fixed catalogue below names the exact target and eligible caller for each supported action.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="cli-automation-authority"></a>

<a id="cli-delivery-and-automation-authority"></a>

<a id="application-workflows-and-human-only-administration"></a>

### Application workflows and human-only administration

SupportBot can update permitted existing configuration through import, upload documents, query Pipelines, run evaluations and accept specific evaluation-case revisions. V1 resource provisioning is human-only: a bot cannot create Projects, groups, accounts, Pipelines, Deployments, Collections, Sources, connections or immutable profiles. The [provisioning contract](#provisioning) distinguishes those resources from versions, Documents, jobs and cases produced by authorized operations. Missing import dependencies require a human provisioning step. Do not fall back to a saved human login.

These actions are not enabled automatically. SupportBot needs permission for each action on the relevant resources, together with access to any required documents and models. Being an application account makes it eligible to receive those permissions. It does not grant them.

Building a version and publishing it require separate permissions. Managing identities, memberships, permissions and provider credentials remains restricted to authorized humans. Running a command from a script does not remove that restriction.

<a id="an-application-cannot-remove-its-own-spending-limit"></a>

#### An application cannot remove its own spending limit

Project spending-policy changes are **human-only in v1**. Alice may set, increase, decrease or remove a project's limit only if she currently has permission to manage that project's spending policy. A human without that permission is denied too.

SupportBot may inspect budget information it is allowed to see and run authorized work within the limits. It cannot change the policy, including through setup or TOML import. Otherwise an automated worker could remove the control intended to contain its spending.

Use `inspect-budget` and the separate human-only `manage-budget`, each on the exact Project, as recorded in the [reviewed catalogue](#reviewed-capability-catalogue). This restriction does not change the separate limits on individual operations or decide who may change unrelated project policies. [Budget management](../../inframeld-application-contracts/references/spending-and-accounting.md#budget-policy-authority) explains the workflow. The model contract still owns its exact policy/accounting schemas and coordination. Budget-policy management implements them.

<a id="initial-project-grants"></a>

<a id="seventeen-explicit-initial-project-grants"></a>

#### Seventeen explicit initial project grants

The fixed list is `manage-project-members`, `create-access-groups`, `create-application-accounts`, `create-pipelines`, `create-deployments`, `manage-upload-defaults`, `delete-project`, `inspect-budget`, `manage-budget`, `manage-trace-policy`, `delete-trace-history`, `inspect-feedback`, `create-collections`, `create-sources`, `create-model-connections`, `create-processing-profiles` and `create-embedding-profiles`.

[The initial-assignment contract](#initial-assignments) owns this list and the enumerated human creator assignments for Pipelines, Deployments, Collections, Sources, connections, profiles and application accounts. [ADR-0059](../../../../docs/adr/ADR-0059-seed-fixed-human-creator-grants-for-v1-resources.md) supersedes the earlier eleven-action seed. These are removable exact-target grants, not an administrator role, future-action wildcard or automatic backfill for existing projects. Pipeline creators receive thirteen assignments. Deployment creators receive seven, including own-feedback authority. Resource grants supply neither document access nor rights on another resource.

For example, Alice keeps her starter and creates Legal Research for a separate workload. Ordinary project administration owns this creation operation:

1. Check that Alice is an eligible human with current installation-level Create projects permission. There is no existing project membership to require yet.
2. Check the reviewed Name and Display name. An unavailable Name fails without silently choosing a different one or revealing another project's owner.
3. Save the project, Alice's membership, the seventeen explicit initial assignments, audit and original-request outcome together. If the transaction fails, none of these partial records remains.
4. Return the committed identity. If the response is lost, recover that original result under current access. Do not create another project or restore grants removed since creation.

Creation alone does not create RAG resources, change the starter or change the CLI's saved selection. Setup and import are separate next operations. If either is interrupted, the completed project remains. CLI access management presents ordinary creation and deletion. Setup uses the same creation operation. Starter provisioning remains a separate responsibility and does not depend on Create projects.

Setup uses stable IDs and uniqueness checks so a retry does not create duplicate defaults. It must not recreate defaults that someone deliberately deleted.

<a id="reviewed-capability-catalogue"></a>

<a id="reviewed-capability-identifiers-and-extra-checks"></a>

### Reviewed capability identifiers and extra checks

Use [the fixed capability catalogue](#capability-catalogue) for the exact identifiers and supported action/target/caller combinations. It preserves `create-access-groups`, `query` and `feedback:write`. Applications receive use-only eligible grants. Human-only creation, grant administration, credentials, audiences and policy changes cannot become application-eligible through import. Current principal/project state, membership and protected-input checks remain additional conditions.

Evaluation uses six separate Pipeline-scoped operational grants and human-only `manage-evaluation-case-audiences`, without per-case grant rows or a generic Dataset/Experiment target. The [Evaluation guide](../../inframeld-evaluation/references/case-audiences.md#case-audiences) owns protected saved import audiences and existing-case changes. [Feedback](../../inframeld-pipelines/references/answer-feedback.md#feedback-authority), [tracing](../../inframeld-pipelines/references/query-tracing-and-privacy.md#trace-authority) and [budget policy](../../inframeld-application-contracts/references/spending-and-accounting.md#budget-policy-authority) own their detailed workflows. Product-facing non-query diagnostic browsing is deferred in v1. Ordinary domain job/case/result inspection remains separately authorized.

<a id="capability-catalogue"></a>

<a id="fixed-action-catalogue"></a>

## Fixed action catalogue

Identifiers use descriptive kebab-case. Preserve the published `create-access-groups` and the already accepted `query` and `feedback:write` literals. Each row is one action on the exact indicated target. A grant on one Pipeline, Deployment, Collection, Source, connection or profile supplies no rights on another. Unsupported action/target or action/principal-kind combinations are denied, including during grant assignment. There are no custom roles or future-action wildcards.

Applications may receive **can use** only for eligible actions. Humans may receive **can use** or **can use and grant**. This is the same authorization model, with deliberate eligibility restrictions. Current principal/project eligibility, membership, credential restrictions and protected-input checks remain necessary. The catalogue does not replace them. Basic visibility and the fixed Edit-includes-View rule follow [Access visibility](memberships-groups-and-handover.md#section-hide-inaccessible-resources).

| Identifier | Exact target | Eligible caller | Meaning and owning checks |
| --- | --- | --- | --- |
| `admit-users` | Organization | Human | Admit verified humans or issue admission invitations. Identity proof and current authority remain separate from login. |
| `suspend-users` | Organization | Human | Immediately block a human even if responsibilities become stranded. |
| `restore-users` | Organization | Human | Deliberately restore a suspended human after identity/security review and required cleanup. |
| `create-projects` | Organization | Human | Create an additional ordinary project. Starter provisioning remains separate. |
| `manage-project-members` | Project | Human | Add/remove eligible members and review membership invitations. Not grant administration. |
| `create-access-groups` | Project | Human | Create a project-local group and explicitly initialize human membership/management. |
| `create-application-accounts` | Project | Human | Create an empty application account and its creator administration assignments. No key or inherited rights. |
| `create-pipelines` | Project | Human | Create a Pipeline and its fixed creator assignments. |
| `create-deployments` | Project | Human | Create a Deployment with a ready compatible initial version and fixed creator assignments. |
| `manage-upload-defaults` | Project | Human | Change future upload audiences, managing every old/new group. |
| `delete-project` | Project | Human | Block and erase project-owned contents under the project-deletion contract. Does not grant reading. |
| `inspect-budget` | Project | Human or application | Inspect permitted budget information. Accounting schemas belong to the model contract. |
| `manage-budget` | Project | Human | Set, raise, lower or remove its limit through the guarded policy operation. |
| `manage-trace-policy` | Project | Human | Change recording/retention within operator policy. Imports use the same checks. |
| `delete-trace-history` | Project | Human | Explicitly erase selected trace history. Ordinary expiry/source erasure remains backend work. |
| `inspect-feedback` | Project | Human or application | Inspect protected reports. Cannot edit another caller's rating. |
| `create-collections` | Project | Human | Create an empty Collection definition. Does not admit Documents. |
| `create-sources` | Project | Human | Create a reviewed source definition with explicit destination groups. Credentials/sync remain separate. |
| `create-model-connections` | Project | Human | Create non-secret connection configuration. Provider credentials and optional testing remain separate. |
| `create-processing-profiles` | Project | Human | Create a named immutable processing definition. Does not process data. |
| `create-embedding-profiles` | Project | Human | Create a named immutable vector definition. Does not generate vectors. |
| `query` | Pipeline or Deployment, separately | Human or application | Execute saved working configuration or released serving selection respectively. Neither target includes the other. |
| `inspect-query-traces` | Pipeline or Deployment, separately | Human or application | Inspect query evidence under current access to every captured source, including uncited candidates. |
| `build-pipeline` | Pipeline | Human or application | Prepare a ready version. Policy-controlled publication additionally needs the selected Deployment's release authority. |
| `view-pipeline-configuration` | Pipeline | Human or application | Read permitted non-secret saved configuration/history without revealing linked inaccessible resources. |
| `edit-pipeline-configuration` | Pipeline | Human or application | Save/restore supported configuration revisions. Does not manage shared connections or publish. |
| `delete-pipeline` | Pipeline | Human or application | Request its narrower guarded lifecycle deletion. Not document erasure or project deletion. |
| `view-deployment-configuration` | Deployment | Human or application | Read permitted non-secret configuration. |
| `edit-deployment-configuration` | Deployment | Human or application | Edit non-serving details. Changing serving selection requires Manage releases. |
| `manage-releases` | Deployment | Human or application | Publish, manage candidates/canaries, rollback, switch mode and select automatic inputs under readiness/revision checks. |
| `delete-deployment` | Deployment | Human or application | Request guarded Deployment deletion. Does not erase underlying Documents. |
| `feedback:write` | Deployment | Human or application | Read/write own live-answer rating with current Query, original principal and protected receipt checks. |
| `generate-evaluation-cases` | Pipeline | Human or application | Separately admit model work and save unreviewed candidates. |
| `view-evaluation-cases` | Pipeline | Human or application | Read/history/export under current case audiences and linked sources. |
| `edit-evaluation-cases` | Pipeline | Human or application | Edit/import/link verified evidence/remove future selection. Changed content is unreviewed. |
| `review-evaluation-cases` | Pipeline | Human or application | Accept/reject exact revisions, recording the actual principal and kind. |
| `run-evaluation` | Pipeline | Human or application | Execute with Pipeline Query and current case/source/model/budget checks. |
| `inspect-evaluation-results` | Pipeline | Human or application | Inspect protected runs/comparisons. Not general diagnostic trace browsing. |
| `manage-evaluation-case-audiences` | Pipeline | Human | Change saved import audience or explicitly selected cases' audiences, managing every old/new group. |
| `view-collection` | Collection | Human or application | Inspect permitted definition/membership metadata. Reading contents still requires document access. |
| `edit-collection` | Collection | Human or application | Change logical corpus membership through ordinary revisions. Not erase Documents or widen audiences. |
| `delete-collection` | Collection | Human or application | Delete the collection definition subject to live dependencies. Does not erase admitted Documents. |
| `view-source-configuration` | Source | Human or application | Inspect permitted non-secret source configuration. |
| `edit-source-configuration` | Source | Human | Change its guarded configuration/destination binding. Does not change existing document audiences. |
| `sync-source` | Source | Human or application | Start bounded sync through ordinary admission, saved group Add/Update rights and collection mutation checks. |
| `manage-source-credentials` | Source | Human | Bind/replace/remove source credentials through protected input. Cannot retrieve stored plaintext. |
| `delete-source` | Source | Human | Stop future sync and retire configuration/credentials. Does not erase already admitted Documents. |
| `view-model-connection-configuration` | Model connection | Human or application | Read permitted non-secret connection configuration. |
| `use-model-connection` | Model connection | Human or application | Use supported roles/models through ModelGateway under current access, credential and spending checks. |
| `manage-model-connection` | Model connection | Human | Guarded shared configuration/credential administration, preserving live-impact and embedding-compatibility checks. |
| `delete-model-connection` | Model connection | Human | Guarded retirement. No silent provider fallback or dependency rebinding. |
| `view-processing-profile` | Processing profile | Human or application | Inspect its immutable permitted definition. |
| `use-processing-profile` | Processing profile | Human or application | Select it for ordinary authorized processing/preparation. |
| `view-embedding-profile` | Embedding profile | Human or application | Inspect its immutable permitted definition. |
| `use-embedding-profile` | Embedding profile | Human or application | Select it for ordinary authorized compatible vector preparation/querying. |
| `add-documents` | Access group | Human or application | Add on every selected audience group. Does not grant document reading. |
| `update-documents` | Access group | Human or application | Update on every authoritative current audience group. Preserve the audience. |
| `delete-documents` | Access group | Human or application | Delete on every current audience group. Erase all Document versions under normal cleanup. |
| `issue-application-keys` | Application account | Human | Exact-account authority plus ability to grant every current account action/manage every account group. |
| `revoke-application-keys` | Application account | Human | Independent revocation authority, including the last key. No issuance delegation requirement. |
| `delete-application-account` | Application account | Human | Retire the account and revoke keys while preserving project-owned work. |

Group membership/management, document sharing and grant administration are guarded relationships/operations, not extra wildcard actions. Grant-management reads and writes require current can-use-and-grant for that exact action/target. For document Add/Update/Delete assignments on an Access group, its current eligible manager may also administer those assignments through the existing group-management relationship. This supplies neither document-operation use nor membership to another group. Own-access inspection is principal-bound. There is no general product audit-browser permission or API. Non-query diagnostic trace browsing is [deferred in v1](../../inframeld-pipelines/references/query-tracing-and-privacy.md#non-query-diagnostics).

<a id="provisioning"></a>

<a id="human-provisioning-and-application-updates"></a>

## Human provisioning and application updates

V1 creation of Projects, access groups, application accounts, Pipelines, Deployments, Collections, Sources, model connections and processing/embedding profiles is human-only. Applications start with no rights and receive only explicit eligible use grants. Application-driven provisioning and the associated human grant-initialization binding are deferred, rather than implemented as an unused interface.

Supported updates to existing resources remain available to applications under their exact grants. A permitted operation may produce Documents, DocumentVersions, CollectionRevisions, configuration revisions, PipelineVersions, jobs, receipts or Evaluation cases/revisions. This is workflow output, not a bypass for creating configurable resources. Human-only source/model administration, audience management, credentials, grants and budget/tracing changes remain human-only even through import.

An application configuration-import plan may reuse compatible existing resources and apply eligible supported updates. A missing resource or changed immutable profile requiring creation makes that plan ineligible. Reject a known-ineligible plan before its mutations. Report the dependency that an authorized human must provision, then allow a new reviewed plan. Never switch to a saved human, invent a replacement profile or silently omit requested work. Later authority/state changes retain the normal partial-outcome and original-operation recovery rules.

<a id="initial-assignments"></a>

<a id="explicit-initial-human-assignments"></a>

## Explicit initial human assignments

Creation checks current human eligibility and the matching Project Create action, then saves the resource, the following exact-resource **can-use-and-grant** assignments, audit and original-request outcome together. No partial resource/grant state remains on transactional failure. Initial assignments are removable grants, not creator authority. A retry recovers the original result without recreating removed grants. New defaults do not automatically backfill existing resources or projects.

| New resource | Fixed creator assignments |
| --- | --- |
| Additional Project | Seventeen: `manage-project-members`, `create-access-groups`, `create-application-accounts`, `create-pipelines`, `create-deployments`, `manage-upload-defaults`, `delete-project`, `inspect-budget`, `manage-budget`, `manage-trace-policy`, `delete-trace-history`, `inspect-feedback`, `create-collections`, `create-sources`, `create-model-connections`, `create-processing-profiles`, `create-embedding-profiles`. Requires Organization `create-projects`. Starter provisioning has its separate admission boundary. |
| Pipeline | Thirteen: `query`, `inspect-query-traces`, `build-pipeline`, `view-pipeline-configuration`, `edit-pipeline-configuration`, `delete-pipeline`, the six Evaluation operational actions above, and `manage-evaluation-case-audiences`. |
| Deployment | Seven: `query`, `inspect-query-traces`, `manage-releases`, `view-deployment-configuration`, `edit-deployment-configuration`, `delete-deployment`, `feedback:write`. A ready compatible initial version is required. |
| Collection | `view-collection`, `edit-collection`, `delete-collection`. |
| Source | `view-source-configuration`, `edit-source-configuration`, `sync-source`, `manage-source-credentials`, `delete-source`. |
| Model connection | `view-model-connection-configuration`, `use-model-connection`, `manage-model-connection`, `delete-model-connection`. |
| Processing profile | `view-processing-profile`, `use-processing-profile`. |
| Embedding profile | `view-embedding-profile`, `use-embedding-profile`. |
| Application account | `issue-application-keys`, `revoke-application-keys`, `delete-application-account`, assigned to the human creator. The application receives no initial actions, groups or key. |

Access-group creation explicitly initializes the eligible human as both ordinary member and manager, without granting unrelated document actions. First-administrator bootstrap retains the four Organization assignments `admit-users`, `suspend-users`, `restore-users` and `create-projects`. Private starter provisioning retains its explicit project/resource/group assignments through the owning workflow and does not grant `create-projects`.

Profiles remain immutable. There is no profile Edit or force-deletion capability in this decision. Normal reference/retention cleanup does not mutate their meaning. These fixed assignments do not supply document membership, provider secrets, model use on other resources or automatic publication authority.

<a id="support-ci-builds-a-version-and-carol-publishes-it"></a>

### Support CI builds a version and Carol publishes it

An authorized automation account can invoke the underlying readiness-only build and authorized evaluation operations without being allowed to publish. It uses its own principal, not a developer's session. The user-facing policy-controlled Build workflow is broader: when its selected Deployment is Automatic, it additionally requires Manage releases on that target. Missing authority fails that requested workflow, not a silent downgrade. Those permissions give it neither membership-administration authority nor access to provider secrets. The API workflow does not require GitHub or an external CI runner.

Carol's Manage releases on Production covers publishing, rollback, candidate and canary control, publication-mode changes, and selecting inputs for automatic updates. V1 keeps these together as one permission on **that Deployment**. It does not split them into publish-only, rollback-only, or canary-only grants.

Manage releases does not include Build on the Pipeline, Delete on Production, or document access. Operations using protected inputs still need permission to use them. Deployment Edit configuration changes non-serving details such as its name and description. Changing the version that serves or its rollout behavior requires Manage releases. Editing a Pipeline draft is separate again.

Release commands check that a version is ready and that the Deployment has not changed since the request was prepared. They also use an idempotency key to recognize repeated requests. Automation follows the same rules as humans. Its audit record identifies the application principal and credential rather than attributing the work to a fictional human.
