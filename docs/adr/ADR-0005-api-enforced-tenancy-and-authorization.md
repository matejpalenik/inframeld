# ADR-0005: Kratos identity and application-owned authorization

**Status:** Accepted — identity, bounded administration, resource-specific grants, the relational access data model, private starter/access defaults, and emergency recovery policy. The remaining action matrix, physical schema details, and implementation still require completion and qualification.

**Date:** 17 September 2026.

**Revised:** 24 September 2026.

**Source:** [Canonical architecture guide](../ARCHITECTURE.md).

**Related:** [Application structure](ADR-0001-modular-application-structure.md), [API contract](ADR-0002-product-owned-openapi-contract.md), [durable jobs and idempotency](ADR-0007-durable-jobs-idempotency-and-recovery.md), [deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md).

## Context

Inframeld has two main kinds of callers: engineers using its web console, **Studio**, and customer applications asking questions through its API. Optional service automation can also build, evaluate, or release pipeline versions when explicitly permitted.

Every protected operation needs to answer two separate questions:

| Question | Responsibility |
| --- | --- |
| **Who is calling?** | **Authentication:** verify a human session or an application credential. |
| **What may this caller do here?** | **Authorization:** check the caller's current project, action, and document permissions. |

A successful login answers only the first question. Alice can have a valid session without access to the Finance project. Removing her Finance membership must remove that access even while her login remains valid.

The same separation applies to customer applications. Recognizing SupportBot's credential does not authorize every document or let the application claim another user's rights.

We need this behavior in both local and production installations, without requiring a cloud identity account. The design must also distinguish signing in through a company's identity provider from operating an OAuth server, and application-level access from future verified access on behalf of individual users.

## Decision

**Ory Kratos owns human identity and sessions. Inframeld owns its account-screen integration and all application authorization. Customer applications use scoped, expiring, revocable opaque credentials.**

The initial document policy uses group allowlists. Integrations act with their own fixed application permissions; verified end-user delegation and Hydra deployment are deferred.

### 1. Keep four identity and access responsibilities separate

An **identity provider** authenticates users. **OpenID Connect (OIDC)** is the sign-in protocol used here to connect to an external provider. An **OAuth issuer** is a different responsibility: issuing access tokens that other applications present when calling an API.

| Responsibility | Example | Selected approach |
| --- | --- | --- |
| **Manage human identity and sessions** | Alice signs in, uses multi-factor authentication (MFA), recovers her account, or logs out. | Kratos owns credentials and sessions. Inframeld supplies the account-screen integration. |
| **Sign in through an external provider** | Alice signs in through the company's configured OIDC provider and receives a Kratos session. | Kratos acts as an OIDC **client**. Deployment-level configuration is included in open-source v1; Hydra is not required. |
| **Issue OAuth/OIDC tokens to other applications** | Inframeld issues scoped access tokens, potentially for an application acting on a user's behalf. | Hydra is the corresponding Ory **issuer**. Its deployment, login/consent integration, and token lifecycle are deferred. |
| **Authenticate and authorize API clients** | A customer application queries permitted documents, or an authorized automation builds a version. | Inframeld verifies the supported credential and applies current project, action, and document rules. This does not inherently require an OAuth server. |

An OAuth token could carry bounded grants in a future implementation. It would not replace current Inframeld document policy.

Selecting Kratos does not select every Ory component or paid feature. Self-hosted Docker Compose and a future Enterprise Edition (EE) cloud offering use the same underlying identity technology.

### 2. Use Kratos's browser session flow for Studio

Human sign-in uses Kratos's supported browser flow through the installation's configured HTTPS origin.

```text
Browser completes the Kratos login flow
    -> Kratos issues a secure, HTTP-only session cookie
    -> Backend validates the session with Kratos /sessions/whoami
    -> Backend maps the verified identity to a stable local user ID
    -> Inframeld checks current application permissions
```

An **HTTP-only cookie** is not readable by browser JavaScript. Studio's Next.js account screens handle the flow state and required **CSRF protection**, which protects against cross-site request forgery. Do not introduce a bearer token stored in browser local storage.

Invalid, expired, or unverifiable sessions **fail closed**: the operation is denied rather than allowed because verification is unavailable. Account recovery, logout, disabled identities, and required MFA behavior must be tested in the actual deployment.

Use the browser flow, not native-application session tokens treated as browser cookies. Auth.js is not required for this integration, and no additional service is introduced to issue JSON Web Tokens (JWTs) as a competing session mechanism.

The recorded integration reference is [Ory's session-management documentation](https://www.ory.com/docs/kratos/session-management/overview).

#### Account screens and secure operation remain Inframeld's work

Kratos is a headless identity service: selecting it does not supply the finished Inframeld account experience.

Inframeld owns the login, account-settings, and recovery integration, secure bootstrap, and required email configuration. The account screens use Kratos's supplied **flow nodes**—the fields and actions described by its flow response—and documented error handling. They must not reimplement password verification or weaken CSRF checks.

Keep Kratos's administrative API private. Use a separate database and database role from the application tables.

#### Map identities explicitly; do not use email as identity

Use stable local user IDs and an explicit mapping from the external **authority** and **subject** to that local identity. The authority identifies the external identity source; the subject identifies the account within that authority.

An email address is neither an immutable identity nor a permission grant. Two issuers reporting the same email must not cause automatic account merging. Linking accounts requires a deliberate, verified flow.

### 3. Include deployment-level external sign-in in OSS v1

**Open-source software (OSS) v1 includes deployment-level OIDC sign-in.** An operator can configure an upstream identity provider for the installation, including its client registration, redirect URI, and protected client secret.

For example, Alice signs in through the configured company provider. Kratos establishes her identity and session. Inframeld then checks her project and group membership.

**Company login does not automatically grant administrator privileges.** An external group claim does not override application membership without an explicitly designed synchronization policy. The upstream provider's token also does not automatically become an accepted Inframeld API credential.

The source ADR records a generic external OIDC provider in the inspected Kratos OSS implementation: [tagged implementation](https://github.com/ory/kratos/blob/v26.2.0/selfservice/strategy/oidc/provider_generic_oidc.go) and [provider configuration](https://www.ory.com/docs/kratos/social-signin/generic).

External sign-in is optional to configure. A local trial still requires authentication, but it does not require a company identity provider or cloud identity account.

#### OSS capabilities and possible EE extensions

| Scope | Treatment |
| --- | --- |
| **First-party login, project API access, and CI/CD credentials** | Included in OSS v1. Here CI/CD covers the application's build, evaluation, and release operations. |
| **Basic access administration needed to use group allowlists safely** | Included in OSS v1. Basic secure operation must not depend on EE. |
| **Deployment-level external OIDC sign-in** | Included in OSS v1; configured by the installation operator. |
| **Organization-managed federation policies and per-organization providers** | Possible later EE packaging, not an implemented or guaranteed capability. |
| **SAML/SCIM lifecycle integration, managed operation, and additional governance** | Possible later EE packaging. SAML concerns federated identity; SCIM concerns account provisioning and lifecycle integration. Verify the selected Ory edition's actual support before promising these features. |

An internal organization ownership boundary does not require a multi-organization administration product now. The documented OSS starting experience is one provisioned organization, private starter projects, and project-local groups, as described in Section 7.

#### Hydra is deferred, not required for external login

Revisit Hydra when Inframeld needs to issue OAuth access tokens or support a delegated-client flow. Its deployment and login/consent integration are not part of v1.

This is sequencing, not a blanket EE restriction. If delegated access becomes necessary for the usefulness of the OSS product, reassess its OSS implementation scope.

Hydra can later sit alongside Kratos without replacing the identity directory. Inframeld's application permission checks remain in place. The recorded reference is [Hydra's role and self-hosted login/consent integration](https://www.ory.com/hydra?amp=1).

### 4. Give applications and automation their own scoped credentials

The primary workflow remains an engineer operating pipelines, evaluations, and releases inside Inframeld through a Kratos session. The primary programmatic consumer is the customer AI application.

Optional automation uses an attributable **service principal**: a stable application identity with explicit project and action permissions. It must not reuse a developer's browser session or receive organization-administration privileges.

Existing query integrations remain query-only unless separately granted another capability. GitHub and an external CI runner are not prerequisites for these API operations.

#### Credential format and lifecycle

Use an **opaque credential**: a high-entropy random secret that Inframeld verifies and associates with a project service principal, rather than treating it as a caller-authored identity claim.

| Requirement | Behavior |
| --- | --- |
| **Secret generation** | Generate a high-entropy random secret. |
| **Stored representation** | Store only a cryptographic verifier/hash, a safe identifier, and a safe display prefix—not the plaintext credential. |
| **Lifetime** | Credentials expire and can be revoked. Check credential validity and the application's current permissions on every request. |
| **Action grants** | Assign Query, Build, Evaluate, and Manage releases explicitly to the application principal within their scopes. Its valid keys use those current grants; v1 has no separate per-key action grants. Query does not imply any of the others. Manage releases is the deployment permission formerly described here as `deploy`; final API identifiers remain to be defined. |
| **Document scope** | A query integration has an explicit document-group **ceiling** on its application account: the maximum document-group scope its current authority permits. Its keys do not carry separate group allowlists. |
| **Ordinary CI permissions** | Exclude membership administration and provider-secret access. |
| **Issuance** | Follow the show-once secret behavior in [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md). |

Section 11 records the accepted bounded administration and grant rules from issue #24's design discussion. Permission and incoming application-credential management are human-only in v1. Issuing or replacing a credential requires both issuance permission for that specific application and authority to grant all of the application's current action, resource, and document-group permissions. Revoke application keys is a separate permission on each application; it does not require grant authority over the application's permissions and may revoke its last key. Valid credentials use the application's current permissions, including later authorized changes, without key replacement. Separate application accounts provide different access boundaries; per-key permission limits are deferred. Credential expiry, revocation, installation/audience binding, and adapter restrictions still apply. The remaining action catalogue and lifetime limits still need decisions.

A future OAuth credential must resolve to the same application principal and policy. It must not create an alternative authorization model.

#### Example: building is not permission to promote

Support CI has `build` and `evaluate`. It can produce a pipeline version and comparison, but it cannot promote that version.

A separately authorized release job has Manage releases on its target Deployment. It supplies the **expected deployment revision**, which protects against overwriting a concurrent change, and an **idempotency key**, which identifies a retry of the same command. It invokes the same release command as a human.

Audit records identify the service principal and the credential used. They must not invent a human actor for automated work.

### 5. Keep document authorization in one application policy

A **group allowlist** records which application groups may access a document. Group membership and document allowlists are application data in PostgreSQL.

Project access and action permission are prerequisites. A document's allowlist narrows access further; it does not grant entry to another project or permission to perform an otherwise forbidden action.

Authentication and session code remain separate from document policy. That separation allows finer permissions later without changing login or rewriting application use cases.

#### The minimum access boundary

An **access context** carries the verified actor, an optional verified delegated end-user subject, the project, and applicable current principal permissions. Credential verification establishes the caller and enforces expiry, revocation, and installation/audience binding. For v1 applications, permission scope comes from the application account, not an independently scoped key or a permission snapshot frozen at issuance.

The **actor** is the caller whose authority has been verified. A **delegated subject** would be a separately verified user the application is permitted to represent. In v1, a human session has a human actor, and a fixed integration has an application actor with no delegated subject.

```text
Verified caller + project + current principal permissions
    -> Application document policy
    -> Authorized retrieval scope
    -> Backend-specific search filter
    -> Current permission checks on returned document identities
```

The document policy determines the permitted retrieval scope and checks returned document identities. The storage/search adapter translates that scope into the backend's filter format. **Callers never supply an authoritative filter or raw group list.**

Use the same policy for source downloads, retrieval, citations, evaluation evidence, and operation/answer-receipt access. An **answer receipt** is the record identifying the answer execution; access to that record also requires the appropriate checks.

Do not place document policy inside Kratos adapters or scatter independent group checks across HTTP handlers. No external relationship engine, general policy language, deny hierarchy, or per-chunk permission system is selected. Exact type names and future finer rules remain implementation/design details, not a requirement to build a generalized authorization framework.

#### Check current access before content is used or disclosed

Filter candidates before retrieval and recheck current permissions on returned document identities before content reaches a reranker, model, evaluator, or caller. A reranker reorders retrieved candidates; it must not receive documents the caller cannot access.

Revocation protects historical document versions too. An old version or evaluation does not retain an old permission grant. The [architecture guide](../ARCHITECTURE.md) records the detailed filtering and in-flight authorization trade-offs.

Reject supplied delegation assertions until a supported verifier exists. A field named `userId` or `subject` is not proof of identity.

### 6. Start with fixed integration access; defer verified user delegation

#### V1: the integration is the actor

An appropriately authorized human assigns the integration its explicit document-group scope, within that human's grant authority. Administrator status alone is insufficient. Inframeld also checks the integration's project membership and query permission for the requested resource.

There is no verified human subject in the request. The application's authority is therefore the same whether Alice or Bob is asking through it.

Suppose `SupportBot` can read `SupportKnowledge` but not `HRPrivate`:

| Request | Inframeld document authority |
| --- | --- |
| Alice asks through SupportBot. | SupportKnowledge only. |
| Bob asks through SupportBot. | SupportKnowledge only. |
| SupportBot supplies `userId: Alice`, an HR group name, or Alice's canary affinity value. | No additional access. Caller-supplied values cannot expand SupportBot's authority; unsupported delegation claims are rejected. |
| A human authorized to grant HRPrivate access explicitly adds it to SupportBot's scope. | Every request using SupportBot's authority can potentially reach HRPrivate. |

A **canary affinity key** is routing data used to keep requests in a consistent rollout group. It is not an authenticated end-user identity.

**Choose an integration scope that is safe for everyone who can invoke it.** Hiding a user-interface control does not enforce individual employee access in Inframeld.

This initial model avoids user-delegation and token-exchange infrastructure. It is unsuitable when one integration must independently preserve each employee's private document permissions. That limitation must be explicit to adopters.

#### Future delegation: verify both the application and the user

Verified end-user delegation is deferred. The application boundary preserves the distinction between actor and subject; it does not implement delegation by accepting a subject field.

A future supported mechanism must prove the user and bind the grant to both the application and the Inframeld API. Verification must cover the trusted issuer, correct audience, expiry, validated token type, and permitted action scope. The **audience** identifies the intended recipient of the token.

An ID token addressed to another client, a guessed user ID, or an arbitrary signed token is insufficient. Do not forward a broad human session cookie to an unrelated integration as the delegation mechanism.

The protocol, issuer, and revocation behavior remain open. Hydra is an option if Inframeld must issue the necessary tokens.

#### Future example: intersect permissions; never combine them into broader access

Suppose `StaffAssistant` is explicitly allowed to query on behalf of verified users and has a ceiling of SupportKnowledge and HRPrivate.

| Application ceiling | Verified user's rights | Effective document access |
| --- | --- | --- |
| SupportKnowledge and HRPrivate | Alice may read both. | Both, provided project membership and the requested action are also permitted. |
| SupportKnowledge and HRPrivate | Bob may read only SupportKnowledge. | SupportKnowledge only. |
| SupportKnowledge only | Alice may read both. | SupportKnowledge only; her HR rights do not expand the application's ceiling. |

Effective access is the **intersection** of application grants, user rights, project membership, and the requested action—not their union. Both the application and the user must permit the access.

Future audit records retain actor `StaffAssistant` and subject `Alice` separately. The authorization adapter establishes their identities and trusted relationship; the document policy evaluates their intersection.

Preserving this boundary does not add token exchange, third-party consent, external group synchronization, or Hydra to v1. Canary affinity supplies neither identity.

### 7. Start users in private projects without manual access setup

Private starter and access defaults are accepted, as recorded in [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md). Their implementation still requires qualification; the design does not require further approval.

The first-answer experience does not ask a new user to manually create an organization, project, and group.

Use one provisioned installation organization. Each admitted human receives a **creator-private starter project** and a **project-local, nonempty private group**.

Secure first-account bootstrap uses a **one-time, operator-controlled claim**. The first arbitrary public signup must not become the administrator.

Project administration and credential/build/deploy actions stay bounded to that project. **Administration alone does not bypass document-reading policy.**

#### Apply real document permissions during upload

Starter uploads inherit the explicitly stored private-group allowlist on the server. Other users and application integrations receive no automatic access.

An authorized change to the project's upload default applies to future document admissions, not historical documents. Here **admission** means accepting a document into the application's managed state.

Later source connectors use explicit Inframeld group selection. They do not automatically propagate source-system access-control lists (ACLs) into application permissions.

Repeated provisioning uses stable IDs and uniqueness checks to avoid duplicates. It must not recreate defaults that were intentionally deleted.

The detailed onboarding section identifies this work as implementable with bootstrap and admission. [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) records provisioning and reversible publication modes. It does not introduce enterprise organization administration or a general role platform.

#### Automatic updates do not grant extra permissions

The publication mode changes how updates are requested; it does not increase the initiating actor's authority.

| Operation | Required authority |
| --- | --- |
| **Automatic source/configuration update** | The initiating actor needs the relevant source or configuration permission, plus Build on the selected Pipeline and Manage releases on the explicit target Deployment. |
| **Change publication mode** | Deploy authority is required. |
| **Enable Automatic updates and apply the selected inputs** | Build authority and valid inputs are also required. |

The worker rechecks current authority. An upload-only or query-only principal is not upgraded because a project uses Automatic updates.

A Deployment consuming the same collection as another Deployment does not inherit that other target's publication authorization. Permission to publish is checked for the explicit target.

### 8. Apply the same boundaries to feedback and MCP

#### Answer feedback

The `feedback:write` grant allows an integration to submit and read **its own current feedback**, only for its eligible answers and while it has current access to the evidence.

Studio readers need feedback-read authority and current evidence permission. Existing query credentials are not silently expanded to include feedback capabilities.

[ADR-0017](ADR-0017-answer-feedback.md) defines the accepted feedback contract.

#### First-party MCP

The **Model Context Protocol (MCP)** provides another way for trusted clients to invoke application operations. The accepted profile uses fixed application authority and the existing bearer-credential verifier for clients that can supply authentication headers.

It does not turn Kratos into an OAuth issuer and does not accept unverified subjects. [ADR-0018](ADR-0018-first-party-mcp-adapter.md) defines the qualification boundary: the supported profile still needs to be tested.

The proposed default selector must require project and query access **before revealing setup state**. Resolving a default target is not a reason to expose information to an unauthorized caller.

### 9. Keep upstream observations separate from deployment guarantees

The source ADR records the following observations as checked on **19 September 2026**. They are recorded upstream evidence, not a new verification, an Inframeld image lock, or completed deployment testing.

| Recorded observation | Limit of the evidence |
| --- | --- |
| **Kratos OSS v26.2.0 and Hydra OSS v26.2.0**, both released on **20 March 2026**, use **Apache-2.0**. | These observed versions are not automatically the qualified Inframeld images. No load test, security audit, or migration test was performed. |
| Ory documents identity/configuration import and compatible core APIs for Ory Network. | This describes a possible migration path, not a tested guarantee that sessions, IDs, and every feature transfer unchanged. |
| Paid/cloud announcements describe **v26.3.3** capabilities. | They do not establish that OSS v26.2.0 includes every advertised capability. Inspect the actual pinned OSS release during implementation. |

Recorded references: [Kratos v26.2.0](https://github.com/ory/kratos/releases/tag/v26.2.0), [Hydra v26.2.0](https://github.com/ory/hydra/releases/tag/v26.2.0), [Apache-2.0 license](https://github.com/ory/kratos/blob/v26.2.0/LICENSE), [Ory Network](https://www.ory.com/network), and [v26.3.3 announcement](https://changelog.ory.com/announcements/ory-network-ory-hydra-ory-kratos-v26-3-3-released).

A future EE offering can run the same Kratos technology in cloud infrastructure or use Ory Network. Preserve stable local IDs and rehearse identity mapping, domain changes, and reauthentication before relying on migration behavior.

Keycloak and ZITADEL were considered previously. They are not alternative deployment choices after the Kratos decision.

### 10. Verify the security boundaries before release

These are required acceptance cases, not completed tests or functionality implemented by this record.

| Area | Required verification |
| --- | --- |
| **Application scope** | Deny commands and queries outside the caller's permissions. Apply current group membership. Reject forged user, group, and issuer assertions. |
| **Session lifecycle** | Exercise local login, recovery, logout, disabled identities, required MFA, invalid/expired sessions, and an unavailable Kratos session check. Unverifiable sessions fail closed. |
| **Browser and administration boundaries** | Test CSRF protection and that identity administration remains private. |
| **External OIDC** | Exercise configured sign-in, issuer and redirect validation, deliberate account linking, and upstream-provider unavailability. |
| **Service credentials** | Reject expired or revoked credentials and test lost key-creation responses against the show-once behavior. |
| **Automation grants** | Prove that a CI principal with build/evaluate grants cannot deploy, administer membership, or access provider secrets. |
| **Fixed integration authority** | Prove that caller-supplied identity cannot expand an integration's document scope and that v1 rejects delegation claims. |
| **Future delegation** | When implemented, test actor/subject binding and both directions of the permission intersection: the user's rights cannot expand the application ceiling, and the application's rights cannot expand the user's access. |

### 11. Bound administration, grants, and recovery

These decisions were accepted during the [issue #24](https://github.com/matejpalenik/inframeld/issues/24) analysis on 23–24 September 2026. They are design requirements, not claims of implemented tables, endpoints, recovery commands, or passing tests. Later analysis must preserve them unless an explicit decision revises this record.

#### Separate administration from access and sharing

Use **server operator** for the person who controls the host, Docker Compose deployment, database, storage, secrets, and backups. That person is inside the infrastructure trust boundary and can inspect data or override application state through privileged server access; application permissions cannot protect plaintext from them. This matches [ADR-0011's operator boundary](ADR-0011-hosted-vercel-and-aws-deployment-profile.md#5-restrict-access-and-resources-for-the-whole-installation).

Use **in-app administrator** for a human acting through explicitly assigned application permissions. An installation-level permission defines its scope; it is not an unrestricted administrator role. The same person may also be the server operator, but their ordinary application session still follows its current grants. V1 has no unrestricted UI superadministrator or automatic document-reading bypass. Privileged server recovery remains the separate maintenance procedure below.

Project and installation administration do not imply document reading, management of every document group, or authority to assign arbitrary permissions. A person may grant only permissions within their explicitly assigned grant authority and scope. They cannot widen their own authority by appointing themselves as another group's manager, modifying grants, or issuing a more powerful integration credential.

Document-group managers are trusted to control disclosure of that group's documents. Separating management from ordinary reading does not make those documents confidential from someone who can give another account access.

Groups use **peer managers**: a manager may explicitly appoint another admitted human project member as a manager of that same group. There is no separate owner-above-managers hierarchy in v1. The starter creator receives an explicit initial manager assignment for the private group. A last manager deliberately leaving an active group must appoint a replacement first; emergency account suspension must remain possible without a replacement.

**Create access groups** is a separate human-only permission on a specific project, using the same can-use and can-use-and-grant levels as other action permissions. An authorized human creator becomes the new group's first manager through an explicit initial assignment. Creating a group confers no authority over existing groups or their documents. Documents become accessible through the new group only when someone authorized to change their access policy assigns them to it. For example, Alice may create and manage Support Team without gaining control over HR or permission to share HR documents. Existing document-policy changes follow the rule below.

#### Separate human admission, suspension, and restoration

**Admit users**, **Suspend users**, and **Restore users** are three separate human-only permissions for the installation's organization, each with the usual can-use and can-use-and-grant levels. Secure, one-time first-administrator bootstrap records explicit initial can-use-and-grant assignments for these permissions to the verified initial administrator. They are ordinary scoped grants subject to the existing handover rules, not an irrevocable administrator bypass.

**Admit users** permits inviting or approving people to join the installation through the controlled identity/admission flow. Admitted humans receive their normal private starter setup. Admission does not grant access to existing projects, groups, resources, or installation-level administration; those require separate authorized assignments. This permission cannot lift an existing account's suspension or change another person's sign-in identity by treating them as a new admission.

**Suspend users** permits immediately blocking a human account in that installation, including an administrator, last group manager, or last action grantor. Preserve recorded memberships and grants, and apply the suspension/recovery rules below. It does not require the suspending person to hold or be able to grant the target's permissions. It confers no ability to restore the account or take over its authority.

**Restore users** separately permits deliberately lifting suspension for the same legitimate human after the required identity verification and security review. For a compromised account, follow the recovery conditions below, including replacement of compromised sign-in methods and invalidation of old sessions. A password reset alone is insufficient, and explicitly removed permissions remain removed. This permission does not create new grants, bypass identity verification, or authorize signing in as another person.

Check the acting human's current admitted/unsuspended status, action grant, and installation scope at each state change. The three permissions do not imply one another or confer document reading, resource administration, credential takeover, or server-operator emergency reassignment authority. Kratos supplies identity/session/recovery behavior; Access controls admission, suspension, and remaining application permissions.

The considered alternatives were operator-only admission, combining admission with suspension, and letting suspension authority also restore accounts. Separate permissions were selected so onboarding, immediate incident response, and restoration can be delegated independently without adding a custom role or approval-workflow engine. The identity integrations and concrete recovery verification still require implementation and qualification under their owning Epic 2 work.

#### Create additional projects with explicit initial authority

**Create projects** is a separate human-only permission for the installation's organization, using the usual can-use and can-use-and-grant levels. It permits creating additional projects in that installation. Check the admitted human's current status and authority when creating the project; possession of a project-level permission elsewhere does not authorize creation.

Secure, one-time bootstrap explicitly grants the verified first in-app administrator **can use and grant Create projects**, alongside the separate Admit users, Suspend users, and Restore users assignments. They may delegate it under the ordinary grant and handover rules. This is an ordinary recorded permission, not an unrestricted administrator role. The alternative of requiring a separate server-operator assignment after bootstrap was rejected as an unnecessary setup step.

Record the creator's membership and explicit initial administration grants on the new project only. For the project-scoped actions agreed here, these are Manage project members, Create access groups, Create application accounts, Create Pipeline, Create Deployment, Manage upload defaults, and Delete project, each with can-use-and-grant authority. These are ordinary recorded grants, not an irrevocable creator role or a wildcard covering future actions/resources. Additional conditions still apply: for example, managing upload defaults also requires management of every affected group. Creation gives no authority over existing projects or their resources and no automatic document-reading bypass.

An admitted human's automatic private starter project remains authorized by [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md)'s controlled onboarding path; it does not require Create projects and does not grant that installation-level permission. Starter provisioning records its own explicit initial project and resource assignments. The alternative of allowing every admitted human to create additional projects was considered. The separate permission was selected so installations can choose who receives it, including granting it broadly when self-service is desired.

#### Authorize deletion of the entire project explicitly

**Delete project** is a separate human-only permission on a specific project, using the usual two grant levels and an explicit initial can-use-and-grant assignment to the project's creator. It authorizes deleting that project and all project-owned contents through [ADR-0014](ADR-0014-data-retention-deletion-and-external-processing.md)'s scoped, resumable deletion process. Check current membership, suspension status, target scope, and Delete project authority when committing the deletion tombstone.

This includes private contents that the deleting human cannot read. The operation does not additionally require each contained resource's ordinary Delete permission, document-group management, or Delete documents on every group. It grants no ability to read, share, or change permissions on those private contents. Assigning Delete project therefore explicitly entrusts the recipient with erasure of the whole project. Neither ordinary project administration nor installation administration implies this permission.

Block affected access and new work before resumable cleanup, including concurrent admissions, issuance, and publication; cleanup must stay within the authorized project and preserve out-of-scope resources. No replacement manager or action grantor is required for resources being deleted with the project. Historical attribution and operational records follow their existing retention/erasure rules. Do not promise immediate physical erasure or expose private contents through deletion status.

The considered alternative was requiring ordinary deletion permissions for every contained resource. The explicit project-wide permission was selected because its destructive scope is clear and project retirement should not depend on assembling all resource-level authority. The per-resource rules still apply when deleting an individual resource from a surviving project.

#### Delete access groups only after dependencies are resolved

A currently authorized human manager may delete their access group only when no Document or active upload/source configuration references it. Resolve those references first through their normal authorized workflows. Deletion must not silently reassign documents, remove the group from document allowlists, or choose replacement upload/source defaults. Check the dependencies and current manager authority when committing deletion so a concurrent admission or configuration change cannot create a dangling reference.

Deleting the unused group removes its memberships, manager assignments, and group-specific grants; it does not delete any documents. No replacement manager or action grantor is required for the group being deleted. This is deletion of the resource itself, not a departure from a surviving group. Historical audit attribution may retain the deleted group's stable identifier.

For example, a Support manager cannot delete Support while a handbook or an active upload default still refers to it. Once authorized changes have resolved those dependencies, the manager may delete the group without first appointing another manager. This dependency restriction follows the principle of PostgreSQL's foreign-key RESTRICT behavior; the manager authority and permitted cleanup are Inframeld's product policy.

#### Authorize changes to a document's access groups

An existing Document's group allowlist may be changed only by a currently authorized human who manages **every group in either its current or proposed allowlist**. This includes groups being removed, added, or retained. The resulting allowlist must remain nonempty, and all groups must belong to the Document's project. Reading or editing document content alone does not authorize changing who may access it.

For example, sharing an HR-only document with Support requires one person who manages both HR and Support. Creating or managing Support alone is insufficient. Changing an allowlist from HR + Support to Support alone also requires management of both groups; removing HR cannot bypass its existing access boundary.

Use the persisted current allowlist and current manager authority when committing the change. A caller-supplied former group list or a stale authorization check cannot establish permission. The policy belongs to the stable Document and therefore continues to protect historical DocumentVersions and their evidence too.

This is a conservative v1 policy: cross-group changes require one human trusted to manage all involved groups. V1 does not introduce a multi-person approval workflow or a separate per-document owner to authorize these changes. An unexpectedly empty stored policy remains fail-closed; it never means public access. Initial policy assignment during new-document admission follows the separate Add documents rule below.

#### Bound admission of new documents

**Add documents** is a separate permission on each access group. A group manager may explicitly grant it within that group without appointing the recipient as a manager. It uses the existing two grant levels: eligible humans may receive can use or can use and grant; applications may receive can use only. Human grant authority remains limited to that action and group.

Admitting a new Document requires current Add documents permission for **every group in its initial allowlist**, with at least one group selected and all groups in the same project as the Document. Project membership and any applicable credential restrictions also apply. A default group selection is not authorization: the server must check the selected groups even when the user did not choose them manually.

This permits humans and fixed-authority integrations to upload new documents within explicitly authorized group scopes. Recording that bounded initial allowlist is part of admission, not authority to change an existing Document's policy or manage group membership. Add documents does not grant reading, replacing, or deleting existing documents. An upload name or deduplication result must not turn this permission into authority to modify an existing Document or its access policy.

For example, Bob with Add documents on Support may admit a new handbook for Support. Selecting HR as an additional group also requires Add documents on HR. Bob receives no ability to browse existing Support documents or change an existing handbook's audience from this permission alone. Uploading does not imply Build or Manage releases; automatic publication still requires its separately authorized workflow.

#### Bound changes to project upload defaults

**Manage upload defaults** is a separate human-only permission on a specific project, using the usual can-use and can-use-and-grant levels. Changing the project's default upload allowlist requires both this permission and current management of **every group in its persisted current or proposed default allowlist**, including groups being added, retained, or removed. Keep the proposed allowlist nonempty and confined to the same project. Neither project permission alone nor group management alone is sufficient. Check the current configuration and authority when committing the change.

For example, changing the upload default from HR to Support requires someone who manages both groups and may manage that project's upload defaults. Managing Support alone cannot redirect future uploads intended for HR. Granting Manage upload defaults does not itself grant management of any group.

The change affects future admissions only; existing Documents retain their stored access policies. Every admission still requires Add documents on every selected group, including defaults, alongside current project membership and any credential restrictions. Changing defaults must not grant upload rights or silently substitute another audience when those checks fail. This decision covers project upload defaults; source-specific configuration authority remains to be designed separately.

#### Bound updates to existing documents

**Update documents** is a separate permission on each access group. Group managers may grant it within their own groups without appointing the recipient as a manager. It uses the existing can-use and can-use-and-grant levels; applications receive can use only.

Replacing an existing Document's content requires current Update documents permission for **every group in its persisted current allowlist**, alongside project membership and any credential restrictions. Check the current policy and authority when committing the update. An empty allowlist remains fail-closed, and a caller-supplied group list cannot narrow the required checks. Add documents alone cannot authorize replacement.

An update preserves the stable Document identity and its access groups. Changed content creates a new immutable DocumentVersion; earlier versions are not rewritten. The existing unchanged-content idempotency rule still applies. Update documents grants no authority to delete the Document, change its audience, or manage group membership. Reading, building, and publication retain their separate authorization requirements.

For example, Bob may update a handbook shared with HR and Support only if he holds Update documents on both groups. Update authority on Support alone cannot change material shared with HR. This rule applies equally to a human contributor and an application with the required bounded permissions.

#### Bound deletion of documents

**Delete documents** is a separate permission on each access group. Group managers may explicitly grant it within their groups, using the existing two grant levels for eligible humans; applications may receive can use only. Add documents and Update documents do not include deletion authority.

Deleting a Document requires current Delete documents permission for **every group in its persisted current allowlist**, alongside project membership and any credential restrictions. Establish this authority against the nonempty current policy when committing the deletion tombstone; an empty policy or a caller-supplied replacement group list cannot bypass the checks. For example, deleting a handbook shared with HR and Support requires Delete documents on both groups.

This operation deletes the Document across all its versions. It is distinct from removing a group's access or omitting the document from a future CollectionRevision. Under [ADR-0014](ADR-0014-data-retention-deletion-and-external-processing.md), deletion blocks access and invalidates affected serving state first, then performs resumable cleanup of in-scope stored data. Historical evidence or Deployments depending on that document may become unavailable; immutable versions and retention pins do not override explicit erasure. Do not promise immediate physical erasure or a broader deletion scope than the authorized Document.

#### Use two grant levels and explicit resources

| Grant level | Authority |
| --- | --- |
| **Can use** | Perform the specified action within its assigned scope. This is the default when sharing permission. |
| **Can use and grant** | Perform the action and explicitly grant, downgrade, or revoke it within that same action and scope. Another eligible human may receive either level; an application may receive only can-use permission. |

Reading or using something alone does not authorize sharing it. Giving another human grant authority is a separate, explicit choice. There is no additional hierarchy of delegation levels.

A human with can-use-and-grant authority may remove another principal's permission for that same action and scope, regardless of who originally granted it. They may also remove another human's grant authority, either retaining can-use permission or removing the permission entirely. The original grantor has no special control after losing their own authority. For example, Carol may revoke Bob's Manage releases permission on Test even if Alice granted it; Carol's Test authority gives her no control over Production. These changes must preserve the last-grantor handover rule below.

Pipeline and Deployment operations use **explicit resource-specific assignments**. Alice may build versions of the Support Pipeline, publish to Test, and query Production without being allowed to publish to Production. Grant authority for Test cannot authorize grants on Production. Project membership remains a prerequisite, and document-group checks remain separate.

**Delete** is a separate permission on each individual Pipeline or Deployment. Editing, building, or publishing does not imply permission to delete. Delete follows the same two grant levels: can use permits deleting that specific resource, while can use and grant also permits explicitly sharing that Delete permission within the same scope. This decision defines authorization, not deletion mechanics, dependency handling, or data-retention behavior.

**Manage releases** is one permission on each individual Deployment, using the same two grant levels. It covers publishing a version; rollback; attaching, starting, adjusting, promoting, rejecting, or stopping a candidate/canary; switching Automatic updates or Manual releases; and selecting the inputs followed by automatic updates. This is the accepted name for the authority earlier described as Publish or `deploy`. V1 does not offer separate publish-only, rollback-only, canary-only, or automation-only grants: a person trusted to roll back is also trusted to publish on that same Deployment. Final API identifiers remain an implementation decision.

Deployment **Edit configuration** covers non-serving details such as its name and description. It cannot change serving targets, rollout settings, publication mode, or automatic-update inputs; those require Manage releases. This distinction applies to Deployment editing, not to Pipeline draft editing. Manage releases does not imply Delete, Build on a Pipeline, or document access. Operations that build or consume protected inputs still require the corresponding permissions. Existing release-state, readiness, concurrency, and current-authorization rules remain mandatory.

V1 has no operational grant covering all current and future Pipelines or Deployments in a project. New resources inherit no existing users' operational permissions automatically. Automatic updates check authority for the exact Pipeline and Deployment involved; sharing a Pipeline or Collection never transfers publication authority between Deployments. Resource identity must remain stable across renames.

**Create Pipeline** and **Create Deployment** are separate project-scoped permissions. When an authorized human creates a resource, creation records explicit can-use-and-grant permissions for that new resource. It grants no extra access to existing resources, documents, or model connections. Starter provisioning creates explicit initial assignments through its authorized setup path; it is not a wildcard grant over future resources.

#### Authorize Deployment creation and initial serving together

For an authorized human, **Create Deployment** on the project permits creating a new Deployment with a selected ready, same-project, contract-compatible PipelineVersion as its initial current version. Commit the Deployment, its initial serving version, and the creator's explicit initial can-use-and-grant permissions together, including **Manage releases on that new Deployment**. There is no separate first-release permission, pre-created empty Deployment, or grant to a future Deployment required by this path. Permission to create does not supply Build, document access, or other protected-input permissions; operations that need them still check them separately.

Before the default Deployment exists, its first automatic publication uses the initiating human's project-scoped Create Deployment authority alongside Build on the selected Pipeline, the ordinary mutation permissions, and access to the selected inputs. Capture the initiating actor and creation intent; recheck current authority before dispatch and at publication. Preserve ADR-0019's existing readiness, expected-state, mode, control-revision, request-identity, and lifecycle checks. Commit the default binding, transferred publication-control state, Deployment, initial version, and initial grants together. A competing creation must not turn this creation request into permission to publish to an existing Deployment.

After creation, every release change requires current **Manage releases on that specific Deployment**. Alice's creation of Deployment A grants her that authority on A, not on Deployment B. The creator's assignments are ordinary permissions subject to handover and revocation, not permanent ownership privileges. The alternative of reserving a future Deployment identity and assigning release grants before it exists was rejected as unnecessary state for this flow.

#### Keep human administration and application execution separate

All permission changes and incoming application-credential management require an appropriately authorized human in v1. Applications receive can-use grants only: they cannot invite people, assign permissions, appoint managers, or issue or manage application credentials. A human identity alone is not sufficient; the required scoped authority must also be checked. Outbound model-provider credential operations remain governed by ADR-0020 and their action matrix.

#### Create application accounts without inherited access

**Create application accounts** is a separate human-only permission on a specific project, using the usual can-use and can-use-and-grant levels. An authorized creation establishes the new application principal in that project with no document-group access, operational action grants, or automatically issued key. Creation must not copy the creator's permissions or give the application human administration capabilities.

Creation explicitly assigns the human creator can-use-and-grant authority for **issuing** and **revoking** keys and **Delete application account** on that new application only. Record these initial assignments with the new account; they confer no authority over existing applications. The creator can delegate these responsibilities under their normal grant rules. Issuance still requires the separate check against all the application's current permissions; creation does not override it.

For example, Alice may create SupportBot and manage its key-administration permissions, but SupportBot cannot query Support documents until authorized people grant its required resource actions and group access. Application permissions and the first key are assigned through their normal authorized operations. The human creator and the application are distinct principals; the application itself receives none of the creator's key-administration authority.

The considered alternative was including application creation in Manage project members. Separate permissions were selected so human membership administration and integration setup can be delegated to different people. Manage project members remains limited to humans. Application deletion uses the explicit initial assignment and rules below, not an implicit privilege attached permanently to being the creator.

#### Delete application accounts without deleting project data

**Delete application account** is a separate human-only permission on that specific application, using the usual can-use and can-use-and-grant levels. The creator receives an explicit initial assignment at both levels. Check current membership, suspension status, scoped deletion authority, and the target application's project when committing deletion. Issuance or revocation authority alone does not authorize account deletion.

Deletion permanently stops the application account, revokes all its keys, and removes its project permissions and group access, as well as human administration grants scoped to that deleted application. Prevent concurrent issuance or grant changes from leaving the deleted account usable. No replacement key administrator or action grantor is required for the deleted application itself. Do not restore the old identity, keys, or permissions by creating another account with the same name.

Project-owned Documents, Pipelines, Deployments, and other project data created by the application remain. Deletion is not permission to erase that data or disclose it to the deleting human. Historical attribution and operational records follow [ADR-0014](ADR-0014-data-retention-deletion-and-external-processing.md)'s retention and erasure rules; do not rewrite the application's past actions as the creator's or promise permanent retention of all history. A retained principal reference or tombstone may identify a retired application without allowing authentication or new work.

The considered alternative was keeping accounts indefinitely and only revoking their keys. Explicit account deletion was selected to retire unused identities and their grants without accumulating active administration state. Key revocation remains the narrower operation when the account should survive.

#### Bound application-credential issuance and replacement

Issuing a new incoming application credential or replacing an existing one requires a currently authorized human who passes **both** checks:

1. The human has permission to issue credentials for that specific application.
2. The human may grant **all of the application's current permissions**, including every action, resource scope, and document-group access, under the existing action-grant and group-administration rules. Ordinary permission to use an action or read a group's documents is insufficient. There is no smaller per-key permission selection in v1.

Issuance does not add permissions to the application, expand its group access, or bypass project membership and suspension checks. Check current issuance and grant authority against the application's current scope when committing issuance, including concurrent grant changes. Replacing a secret is a new issuance decision: an earlier credential or approval is not evidence of current authority. Keep the stable application principal and follow the existing show-once secret rules.

For example, Alice may issue SupportBot credentials but cannot grant HR access. If another authorized person gave SupportBot HR access, Alice cannot now issue or replace any SupportBot credential. A human with both required authorities must do so. This deliberately rejects allowing a trusted key manager to issue credentials solely because they manage the application's keys. Previously issued valid keys follow later changes to application permissions as described below; the issuance checks do not impose a permanent ceiling based on the issuer's former authority.

Credential lifetime limits and the remaining application-principal lifecycle still require decisions. Application-specific issuance is an action in the existing grant model; its permission does not itself confer the underlying grants required by the second check. Replacement and revocation follow the separate rules below.

#### Replace keys with a bounded overlap

An application may have **at most two usable keys** at once: one in use and one for replacement. For this limit, count all unexpired, non-revoked credentials for that application across their supported audiences. Expired or revoked credential metadata may remain under normal retention without occupying a usable-key slot. Enforce the limit when committing issuance so concurrent requests cannot create a third usable key. Do not silently revoke or replace an existing key to make room.

Normal replacement is: issue a second key while the first remains valid, update and test the integration, then explicitly revoke the old key. Creating the replacement never automatically revokes the old one. Each issuance and revocation uses its existing permission checks; there is no separate Rotate permission and the actors may perform the steps separately. Key expiry still applies during overlap; numerical lifetime limits remain undecided. A compromised key should be revoked immediately rather than kept usable until replacement is convenient.

The alternative was permitting many concurrent keys for independently managed consumers. Two were selected for the v1 model of a separate application account per integration, with a spare key for replacement. AWS's documented overlapping-key replacement illustrates the availability pattern; its additional deactivation/reactivation workflow is not introduced by this decision.

#### Separate key revocation from issuance

**Revoke application keys** is a separate human-only permission on each specific application, using the usual can-use and can-use-and-grant levels. Can use permits revoking that application's credentials. Can use and grant additionally permits assigning or managing this same revocation permission for eligible humans on that application. Check current project membership, suspension status, scoped revocation authority, and the credential's application binding when committing revocation.

Revocation does **not** require issuance permission or authority to grant the application's action/resource/document-group permissions. It grants no ability to issue a replacement key, act as the application, read its documents, or change its permissions. Issuance permission does not implicitly include revocation either; assign the two separately where both responsibilities are needed.

For example, Bob may revoke a leaked HRBot key even if he cannot read HR documents or grant HR access. He still cannot issue a replacement unless he passes the two issuance checks. Revoking the last usable key is allowed without arranging a replacement first, even though the integration cannot authenticate again until an authorized replacement is issued. This does not remove the application account, its grants, or its human administrators, and does not bypass their separate handover rules.

The considered alternative was one Manage keys permission covering issuance and revocation, with the extra grant-authority check retained for issuance. Separate permissions were selected so shutdown responsibility can be assigned independently of key creation. As with other revocation, enforce it at subsequent authentication and applicable current-authorization checks; do not claim to recall already-dispatched work.

#### Keep permissions on the application account

In v1, an incoming credential authenticates a stable application principal. The application account holds its current project, resource-action, and document-group permissions. Every valid key for that account uses those current permissions, subject to ordinary credential validity, audience binding, and the operations exposed by its adapter. Permission additions and removals apply to existing keys without issuing new secrets; expiry or revocation still makes an individual key unusable. Evaluate current authorization on each request and at the existing final dispatch/disclosure checks, rather than caching issuance-time grants as authority.

For example, an authorized grant of HR access to SupportBot also enables its already-issued valid keys to use HR access. Removing Support access from SupportBot removes it for all its keys. Whoever grants additional application permissions must understand that the change authorizes everyone able to use an existing valid key, including a previous issuer who retained one. A key is not a human session and does not inherit the current personal permissions of whoever created it.

Use separate application accounts, such as SupportBot and HRBot, when integrations need different access boundaries. Separate keys for the same account distinguish credentials and support rotation/revocation, but do not create different action or document-group scopes. Fine-grained permissions remain on each account; this does not introduce project-wide wildcard resource grants or human delegation.

The considered alternative was a fixed maximum action/resource/group scope on each key, intersected with the application's current rights. It is deferred because v1 does not require differently scoped keys for one account, and keeping one permission layer simplifies configuration and changes. This supersedes the proposed per-key ceiling; the accepted two issuance checks now cover the application's full current permissions. AWS IAM user keys and request-time policy evaluation illustrate the identity/permission separation. Inframeld is adopting that principle, not AWS's full policy language, permission-administration rules, or credential-lifetime practices.

#### Manage project membership without granting resource access

**Manage project members** is a separate project-scoped permission, available only to humans in v1. Can use permits adding already admitted Inframeld human users to that project and removing human members. Can use and grant additionally permits assigning, downgrading, or revoking this same permission for eligible humans within that project. It does not authorize admitting new accounts to the installation or managing membership in another project.

Adding someone records project membership only. It grants no document-group membership, group-manager authority, or Pipeline/Deployment permissions. Those require separate assignments by people with the relevant grant authority. For example, Alice may add Bob to Support, but the people authorized to share Support's documents and resources must separately give Bob access to them.

Removing a member clears that person's project grants and group memberships under the existing removal rule, without revoking grants they previously made to others. Normal removal must preserve the last-group-manager and last-action-grantor handover requirements; Manage project members is not a bypass. Emergency account suspension remains separate. Application-principal membership and credential lifecycle remain part of the unfinished integration-administration matrix.

#### Preserve grants to others; remove a departing member's own access

A grant remains effective until explicitly revoked, even if the person who originally granted it leaves or loses their own authority. This applies to ordinary permissions and peer-manager assignments. Record who made the grant, but do not implement a cascading delegation tree that removes every recipient when a grantor departs.

Removing someone from a project removes that person's permissions and group memberships in the project. Inviting the same stable principal back does not reactivate those old assignments; permissions must be granted afresh. This removal does not revoke permissions they previously granted to other people. Normal departure must respect both the last-group-manager and last-action-grantor replacement rules.

#### Preserve someone who can manage each action permission

While a resource exists, a normal departure, removal, or downgrade must leave at least one active eligible human with can-use-and-grant authority for each affected action in its owning scope. Project/resource grants require a current project member; installation-level grants require an admitted human in that installation. A suspended account or application principal cannot satisfy this requirement. The last human with that authority must first give it to an eligible replacement. Apply this rule to project removal as well as direct grant changes; neither path may bypass the handover requirement. Concurrent ordinary changes must not jointly remove the final eligible grantor.

For example, if Alice alone can grant Manage releases on Production, she must pass that authority to Bob before leaving or giving it up. Bob needs only that specific authority, not control of every Production action. Different people may manage different action permissions. The rule does not require retaining grantors for a resource after its authorized deletion.

Emergency suspension always takes precedence, even when it leaves no active human able to manage an action permission. Recover the same account or, if that is not possible, use the narrowly scoped server-operator procedure below to restore the specific missing grant authority. This does not permit an ordinary project or installation administrator to take over that authority.

#### Hide inaccessible resources

Any currently effective permission on an individual Pipeline or Deployment, at either grant level, permits seeing its basic summary: name, ID, and basic availability status. No additional permission is required to include that resource in the caller's list or show this summary. The permission must remain usable under the caller's current membership, suspension state, and any applicable credential limits; a stored but ineffective grant does not confer visibility.

Basic visibility does not authorize reading configuration, documents, or other sensitive details. Those require their own access checks. Access to a Deployment does not automatically reveal its underlying Pipeline or other linked resources. For example, Alice's Query permission on Production lets her find and select Production; it does not let her inspect the Pipeline configuration or browse documents.

**View configuration** is an independently grantable permission on each individual Pipeline or Deployment, using the same can-use and can-use-and-grant levels. It permits read-only inspection of that resource's settings without granting permission to edit, build, publish, delete, or run another operation. One View configuration permission covers the resource's readable settings; this does not introduce a grant for every configuration field. Document access and disclosure of linked private resources still require their own checks. Saved API keys are never exposed through configuration viewing. Query permission alone provides only the basic resource summary, not configuration browsing.

**Edit configuration includes viewing that same resource's configuration.** A caller may inspect the readable settings when either View configuration or Edit configuration is effective; an editor does not need a separate View grant. View alone remains read-only. Both paths preserve the same document, linked-resource, and secret boundaries.

Removing a standalone View grant does not hide configuration while Edit remains effective. Removing Edit leaves read-only access only if a separate effective View grant remains. To remove configuration access entirely, neither permission may remain effective. This is a fixed implication between these two actions, not a configurable permission hierarchy.

Ordinary Edit confers no sharing authority. A human authorized to grant Edit can give its recipient both editing and the included viewing capability, within the same resource scope. This does not by itself authorize managing standalone View grants; those remain subject to the exact-action grant rule. For example, Bob with View on Support can inspect its settings, while Alice with Edit on Support can inspect and change them. Exact readable/editable fields, handling of protected references, and history visibility remain to be specified in the action matrix.

Resources outside a caller's permitted visibility are omitted from lists and return the same safe not-found result as nonexistent resources when referenced directly. If the caller is allowed to know a resource exists but lacks the requested action, return access denied instead. The HTTP adapter maps these to 404 and 403 respectively using the existing RFC 9457 contract. Project membership does not imply visibility of every resource.

For example, Bob can see Test but has no access to Production. Production is absent from his deployment list and a guessed Production reference returns 404. Attempting to publish to visible Test without Manage releases permission returns 403. [RFC 9110 section 15.5.4](https://www.rfc-editor.org/rfc/rfc9110.html#section-15.5.4) permits concealing a forbidden resource with 404; the owning application policy chooses when existence is private.

#### Limit project, group, application, and administration visibility

Current project members may see the project's **name and ID**, subject to current status and applicable credential checks. Membership reveals neither every resource in that project nor its protected contents. Installation-level permissions such as Admit users or Create projects do not reveal other private projects. The alternative of showing all project names to installation administrators was rejected.

A human holding any current administration permission on a specific application account—Issue application keys, Revoke application keys, or Delete application account—may see that application's **name and ID**, subject to current project membership and status checks. Authorized project grantors may also see eligible applications through the limited recipient directory below. Neither route reveals keys or unrelated application permissions. Being a project member alone does not list every application account; that broader alternative was rejected.

An access group's **name and ID** are visible to its current members, its managers, and callers with an action permission on that group, such as Add documents. Apply current membership, suspension, and credential-validity checks. Other groups remain hidden under the normal list-omission and safe-not-found rules. Basic group visibility does not confer document reading or access to its membership list. Group managers may inspect their group's members and managers. The alternative of listing every project group to every member was rejected because group names themselves may disclose sensitive information.

Humans may inspect **their own permissions**. A currently authorized human who may grant a particular action may inspect that action's assignments within the exact scope they administer, including the assigned grant level. This does not reveal the recipient's unrelated permissions or a resource's complete sharing list. Ordinary use alone does not authorize inspecting everyone else's grants. For example, someone who can grant Build on the Support Pipeline may inspect its Build assignments, not Manage releases assignments on Production. Group-manager membership visibility remains the separate rule above.

Authorized project grantors receive a **basic directory of eligible project users and applications** to select grant recipients. Return only the identity information needed for selection, such as stable ID, display name, and human/application kind; eligibility and scope still follow the normal grant rules. This limited recipient view does not disclose their other group memberships, resource access, application grants, credentials, or private project contents. It does not create a general installation-wide directory or grant this view to every project member. The alternative of making a resource's complete sharing list visible to all its users was rejected to avoid exposing unrelated access relationships.

Humans holding **issuance or revocation permission for a specific application** may list that application's safe key metadata: identifier, safe display prefix, creation/expiry dates, and status. Current membership, suspension, and application scope checks apply. Stored verifiers/hashes and secrets are never returned through this view; the existing show-once creation result remains separate. Listing metadata requires the relevant key-administration permission, not authority over all of the application's underlying grants; the latter is an extra requirement for issuance itself. Directory visibility or Delete application account alone does not imply this key-metadata access. No separate View application keys permission is added in v1; a read-only audit permission remains a deferred alternative if a concrete need arises. This policy does not add credential-administration MCP tools.

#### Suspend a compromised account without destroying its identity

**Suspension** prevents the account from acting immediately while preserving its recorded memberships and permissions. It is different from project removal. Block a compromised account even if it is the only group manager or the only human able to grant a particular action permission. Other currently authorized users retain their own access; management may be unavailable until recovery.

Prefer recovery of the same stable human principal. Verify the legitimate person's identity, replace compromised sign-in methods, invalidate old sessions, and review suspicious permission and credential changes before deliberately lifting the security suspension. A password reset alone does not lift it. Recovery never reinstates memberships or grants that were explicitly removed while the account was suspended.

Kratos owns identity recovery; Access owns whether the recovered account may act and which permissions remain. [Ory's recovery documentation](https://www.ory.com/docs/kratos/self-service/flows/account-recovery-password-reset) and [OWASP's recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html) are integration references, not evidence that the selected deployment's complete incident-recovery flow has been qualified.

#### Recover stranded administration through the server operator

If the legitimate manager or last action grantor cannot return, accept a narrow **server-operator emergency recovery procedure**. It requires privileged server access, identifies the exact group or action/resource scope and verified replacement human account, preserves project/group/resource scope constraints, and records who performed the recovery, the reason, and the authority changed. For an action permission, restore can-use-and-grant authority only for the specific missing action and resource. The compromised account remains blocked. This is a separate maintenance operation, not an automatic takeover privilege for an ordinary in-app installation administrator.

The server operator is trusted with the infrastructure and database. The recovery procedure gives that operator explicit reassignment power and can therefore enable document access or the recovered action. Recording the action supports accountability; it does not prevent a trusted operator from misusing that power. Prefer an existing peer with the required authority or recovery of the original account before using this last resort. Exact operator verification, command/API shape, audit storage, and concurrency handling still require design and qualification.

#### Use documented conventions without adding a permissions platform

The design and tests should use these references for specific properties:

| Reference | Application here |
| --- | --- |
| [OWASP ASVS 5.0, V8](https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.json) | V8.1.1 documents access rules; V8.2.1–2 distinguish action and object access; V8.3.1 places enforcement in trusted server code; V8.4.1 requires tenant isolation. |
| [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html) | Least privilege, deny by default, authorization on every request, and behavioral tests. |
| [OWASP API3:2023 property-level authorization](https://api-security.owasp.org/editions/2023/en/0xa3-broken-object-property-level-authorization/) | Authorization to use a resource does not permit exposing every field. Return only fields the caller may read; basic summaries do not disclose configuration or linked resources automatically. The precise summary policy is Inframeld's product decision. |
| [PostgreSQL grant option](https://www.postgresql.org/docs/18/sql-grant.html) | An established distinction between using a privilege and granting it. Inframeld does not adopt PostgreSQL's entire ownership or cascading-revocation model, or create a database role per product user. |
| [PostgreSQL foreign-key deletion rules](https://www.postgresql.org/docs/18/ddl-constraints.html#DDL-CONSTRAINTS-FK) | RESTRICT prevents deletion of a referenced row. Use this dependency-protection principle for access groups; deleting a group must not cascade into document deletion or silently change document policies. |
| [Kubernetes escalation prevention](https://kubernetes.io/docs/reference/access-authn-authz/rbac/#privilege-escalation-prevention-and-bootstrapping) | Assigning permissions must itself be bounded by the caller's authority. This is a design reference, not a deployment dependency. |
| [Google Cloud service-account security](https://docs.cloud.google.com/iam/docs/best-practices-service-accounts) | Creating a service-account key can let its creator act with that account's authority. Inframeld therefore treats incoming credential issuance as an access-granting operation; the two required issuance checks are Inframeld's own product policy. |
| [AWS IAM access keys](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html) and [policy evaluation](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_policies_evaluation-logic.html) | Keys authenticate an identity; applicable policies authorize requests. This supports keeping v1 application permissions on the account and applying authorized changes to existing valid keys, without adopting AWS's wider IAM model. |
| [AWS access-key replacement](https://docs.aws.amazon.com/IAM/latest/UserGuide/id-credentials-access-keys-update.html) | Overlap the old and replacement keys while consumers are updated and verified. Inframeld selects at most two usable keys and its existing separate issuance/revocation permissions; this does not adopt every AWS key lifecycle operation. |
| [GitHub organization ownership handover](https://docs.github.com/en/organizations/managing-organization-settings/transferring-organization-ownership) | A sole organization owner appoints another owner before leaving. Inframeld's handover requirement for each action permission is its own product policy, using the same continuity principle. |

These selected requirements are not a claim of full ASVS compliance or a reason to introduce an external policy engine, custom role designer, nested groups, or delegated-user authentication.

#### Finish the matrix and preserve issue boundaries

The following table consolidates the accepted administration decisions and related operational boundaries. Each action listed in a cell is independently grantable; the cell is not a bundled role. Named actions use can use or can use and grant. Applications receive only can use for eligible operations; admission, membership/grant changes, and incoming credential/account administration remain human-only. Group management is a separate peer-manager assignment. These are descriptive names, not final API identifiers, and this table does not define the complete future operational catalogue.

| Scope | Separate actions or authority | Additional boundary |
| --- | --- | --- |
| Installation organization | Admit users; Suspend users; Restore users; Create projects | Human-only. Admission, blocking, restoration, and additional-project creation do not imply one another or access to existing private projects. |
| Project | Manage project members; Create access groups; Create application accounts | Human-only. Group/application creation records the accepted initial authority on that new resource only. Human membership alone grants no resource or group access. |
| Project | Create Pipeline; Create Deployment | Separate creation permissions. Authorized human creation records explicit initial grants for the new resource. Deployment creation includes its initial ready serving version and Manage releases grant; no authority over other resources. |
| Project | Manage upload defaults | Human-only, plus management of every current or proposed group. Affects future admissions only. |
| Project | Delete project | Human-only. Explicitly covers all project-owned contents, including unreadable private contents, without granting read access. |
| Individual Pipeline or Deployment | View configuration; Edit configuration; Delete | Separate resource grants. Edit includes viewing the same configuration; Delete is independent. Protected references and secrets retain their own checks. |
| Individual Deployment | Manage releases | Covers publication, rollback, canaries, publication mode, and automatic inputs. Build and document access remain separate. |
| Access group | Peer-manager assignment | Human-only. Controls that group's membership and managers; unused-group deletion requires dependency checks. No authority over other groups. |
| Access group | Add documents; Update documents; Delete documents | Independently grantable; applications may use. Add checks every initial group; Update/Delete check every persisted current group. No implied document reading. |
| Document policy | Management of every current or proposed group | One authorized human must pass all checks. Nonempty same-project policy; no separate per-document owner or approval workflow. |
| Individual application account | Issue application keys | Human-only, plus authority to grant all current application permissions. At most two usable keys; no automatically issued key. |
| Individual application account | Revoke application keys | Human-only. Independent of issuance and the application's underlying grants; may revoke the last key immediately. |
| Individual application account | Delete application account | Human-only. Retires the identity, keys, and its grants; preserves project-owned data. |
| Exact action and scope | Can use and grant | Human-only. May grant, downgrade, or revoke that action within that scope, preserving ordinary handover rules. |
| Exact stranded group or action scope | Server-operator emergency recovery | Privileged maintenance with verified replacement and recorded actor/reason/change; no ordinary in-app takeover. |

Basic visibility is derived from the accepted relationships, without a new universal View permission:

| Visible information | Eligible caller |
| --- | --- |
| Project name and ID | Current project member. |
| Pipeline/Deployment name, ID, and basic availability | Holder of a currently effective action on that resource. |
| Group name and ID | Current member, manager, or holder of an action on that group. |
| Application name and ID | Human with an administration action on that account, or an authorized grantor using the eligible-recipient directory. |
| Group members and managers | Current human manager of that group. |
| Action assignments and grant levels | Human able to grant that exact action in that exact scope; humans may also inspect their own permissions. |
| Safe application-key metadata | Human with Issue or Revoke permission on that application. |

All rows retain current membership/status/credential checks where applicable and the normal hidden-list, safe-404, and visible-but-forbidden-403 rules. Basic visibility never grants protected content or unrelated access relationships.

The accepted Create Deployment rule supplies authority for initial creation and serving, including the first automatic default publication, without a placeholder Deployment or wildcard grant. The full future operational catalogue, exact configuration fields and protected-reference handling, history and other resource views, source/collection operations, credential lifetime limits, and detailed identity-verification/handover/emergency-recovery mechanisms must be settled with their owning workflows. They are not implicit permissions, and should not expand issue #24 into all those features. Do not silently fill gaps with administrator bypasses or wildcard grants.

Issue #24 establishes verified principals, application-owned policy/contracts, the agreed administration matrix, scoped database constraints, and appropriate behavior tests. Kratos session/recovery integration belongs with #25; starter provisioning with #27; administration and ownership workflows with #28; bulk document/evidence checks with #29; and incoming credential lifecycle with #30. Emergency-recovery delivery must be explicitly included in the relevant Epic 2 administration work; this record does not claim the existing issue already specifies its full implementation. Defining resource-specific policy does not authorize implementing future Pipeline or Deployment features in #24.

### 12. Persist the accepted access data model

The issue #24 discussion on 24 September 2026 accepted **one principal model for humans and applications**, with authentication details kept separate, and **individual relational grant records with explicit target relationships**. This section records that model and the implications of section 11's policy. It is the detailed source for implementation; the architecture guide and Access skill summarize it.

These are logical records and consistency requirements, not final SQL table names, column types, ORM classes, or implemented behavior. One logical concept does not require a separate aggregate, repository, service, or public endpoint. Access still belongs to the single backend described in ADR-0001.

#### Records and their relationships

| Logical record | Information it represents | Boundary to preserve |
| --- | --- | --- |
| **Principal** | Stable local identity, human/application kind, and account status used by Access. | Both kinds use the same membership and action-policy model. The shared model does not make applications eligible for human-only administration. Account kind and status are trusted application facts, not caller-supplied claims. |
| **Identity link** | External authority and subject mapped to a local human principal. | An authority identifies the verified identity source; a subject identifies the account within it. The same external identity must not resolve ambiguously to different local humans. Email, display name, or an upstream group is not the identity key. |
| **Organization** | The installation's ownership and installation-action scope. | V1 provisions one installation organization. Recording the boundary does not add multi-organization administration or enterprise federation. |
| **Project** | Stable project identity and its owning organization. | A resource belongs to its recorded project. Project membership and project-scoped authority do not extend to another project or to installation-level actions. |
| **Project membership** | A relationship between a principal and a project. | Membership is a prerequisite for project operations, not an action grant or document-reading grant. Human membership administration and application-account creation/removal follow their separate section 11 workflows. |
| **Access group** | Stable group identity and its owning project. | It defines a document audience within that project. Documents refer to groups through their stored allowlists; a group is not a bundle of all project operations. |
| **Group membership** | A principal's document access through one project-local group. | It is separate from project membership, group management, and operational action grants. Application group relationships define the application's current document scope, not a per-key copy. |
| **Group manager assignment** | A human's peer-manager authority on one project-local group. | Keep it distinct from ordinary group membership. A manager may control disclosure through authorized sharing but does not gain an implicit ordinary read bypass. Only eligible humans may hold this assignment. |
| **Action grant** | A principal, one action, its exact scope/target, its grant level, and assignment attribution. | Record grants individually. Human recipients may have can use or can use and grant; application recipients may have only can use for eligible actions. Neither a valid identity nor general administrator status supplies an absent permission. |

The common principal identity is the reference used by memberships, grants, and attribution. Human sign-in mappings and application credentials establish which principal is acting; they do not create parallel human and application permission systems. Human-specific or application-specific persistence may remain separate where needed without duplicating the shared authorization model.

An application account is established in its owning project through the accepted creation workflow. It starts without document access, operational grants, or an automatically issued key. Do not interpret a common principal model as permission to move an application between projects or copy its creator's rights. A human may be explicitly admitted to multiple projects under their membership rules.

#### Keep identity and credential lifecycles separate

For a human request, the verified Kratos identity resolves through the explicit identity link to the stable local principal. Kratos continues to own sign-in credentials and sessions; application permission records do not contain passwords or Kratos session objects. The authority/subject mapping is not permission to accept an unverified upstream identity or automatically link accounts with matching email addresses.

For an application request, a verified incoming key resolves to the stable application principal. Its verifier, safe metadata, expiry, revocation, and audience/resource binding belong to the credential lifecycle in issue #30. They are separate from the principal's current action grants and group relationships. A key replacement preserves the principal and its permissions; multiple usable keys identify the same account and use its current permissions. The accepted limit remains two usable keys per application, with historical expired/revoked metadata treated separately.

Names and credentials may change without changing the local principal identity. A newly created account with a reused display name does not acquire the retired account's identity or grants. Historical attribution follows ADR-0014's retention rules; a retained historical reference never authorizes new work.

#### What one action grant means

The logical contents of a grant are:

| Information | Meaning |
| --- | --- |
| **Recipient principal** | The human or application receiving authority. |
| **Action** | One supported operation, such as Query or Manage releases. Validate the action against its allowed scope and recipient kind. |
| **Exact target and owning scope** | The installation organization, project, group, or individual resource to which the action applies. A resource grant identifies that resource, not every current/future resource of its kind. |
| **May grant onward** | Whether the recipient has can-use-and-grant authority for this same action and scope. Both grant levels permit use; can-use-and-grant is not a grant-only third level. |
| **Assignment attribution** | Who assigned the permission and when, with later changes recorded according to the audit/retention design. Attribution does not give the original grantor permanent control. |

For example, a grant to Alice of Manage releases on Deployment A with grant authority says nothing about Deployment B, Pipeline Build, document reading, or standalone View assignments. Shared assignment logic must preserve the fixed, accepted implications such as Edit configuration including viewing that same configuration. It must not infer additional implications from action names or implement a configurable role hierarchy.

The subsequent schema discussion accepted **one current assignment per recipient, action, and exact target**, enforced by a database unique constraint. A second grantor changes that assignment through the authorized workflow; it does not create a second independent source of the same permission. Removing the assignment therefore cannot leave an unnoticed duplicate behind.

Use a required boolean **`can_grant`** for the two levels. The current row supplies use authority, subject to the ordinary eligibility checks; `can_grant = true` additionally permits granting that same action on that target. `false` is use-only, not an explicit deny. Applications cannot hold `true`. Fixed implications such as Edit including View remain application policy and do not create extra stored View assignments.

Keep a **fixed action catalogue in application code**. Each supported action declares its target kind and eligible recipient kinds; unsupported actions fail closed. There is no user-editable actions table, custom role language, or runtime permission-definition service. Adding an action requires a reviewed code change and any corresponding persistence constraints. Exact action identifiers and future operational actions remain subject to their owning feature decisions; this choice does not silently complete that catalogue.

Store assignment facts as individual relational records rather than one authoritative JSON permissions document per account. References and relationships must remain explicit even if a public read response later groups permissions for display.

Grantor identity records provenance, not a chain of continuing authorization dependencies. If Alice grants Bob Query and later leaves, Bob's authorized grant survives. Alice's own project grants and group relationships are removed through the normal departure rules. Do not introduce cascading revocation from the original grantor or make multiple duplicate rows an unintended source of residual access.

#### Organize grant tables by target type

The physical organization accepted on 24 September 2026 uses **separate grant tables for organization, project, group, and each supported resource target type**. All actions for a given target type share its grant table. For example, Query and Manage releases on Deployments are records in the same Deployment-grants table; this is not a table per action, recipient, or resource instance.

Each table references its real target and owning scope using the scoped foreign-key rules below. Project-owned application accounts, Pipelines, and Deployments therefore use their respective target-specific grants when those real resources are introduced. Organization-level grants retain installation scope rather than requiring an artificial project. Add future resource grant tables with their owning features; issue #24 does not pre-create unrelated domain resources to support them.

These tables share one application-level permission model and the two accepted grant levels. Separate persistence tables do not require separate permission algorithms, public services, or a repository abstraction for every table. Exact table names and column definitions remain implementation choices to review.

The alternative of one grant table with several optional target columns and an exactly-one-target constraint was considered. It can preserve integrity, but target-specific tables were selected for simpler foreign keys and scope constraints as resource types are introduced. A free-form target type/ID pair with no real foreign key remains insufficient.

#### Separate current grants from permission history

**Current grant tables contain the current assignments.** Successful revocation removes the relevant assignment from its grant table; it does not retain that revoked assignment there behind an inactive flag. A downgrade updates the current grant level. A separate audit record captures who changed which recipient/action/target, the relevant change, and when. The current-state change and its audit record commit in the **same transaction**; failure must not leave only one side committed.

Authorization reads current assignments and applies the normal status, membership, scope, and additional operation checks. It does not reconstruct authority from audit history or treat a historical assignment as a fallback. An authorized later regrant is a fresh current assignment with attribution, not reactivation by accidentally including a retained historical row. This is ordinary current-state persistence with audit records, not an event-sourced authorization engine.

For example, revoking SupportBot's Query grant removes that assignment from the relevant resource-grants table while recording the revocation separately. Its valid key and project membership cannot restore Query. **Suspension is different:** it blocks the principal while keeping its recorded assignments; a current assignment is not necessarily currently usable. Key revocation and application deletion retain their separate lifecycle rules.

History follows ADR-0014's existing retention, access, and erasure boundaries; it is not a permanent copy of sensitive data. Do not store credential secrets or use audit actor/resource references to authorize new actions. The exact audit schema, visibility, indexes, and retention implementation remain to be designed with the owning workflows.

The alternative of keeping revoked assignments in the grant tables with an inactive flag was rejected because every authorization query would have to exclude them correctly. This decision concerns action-grant state and history; it does not remove the distinct suspension or resource-tombstone states required elsewhere.

#### Use database constraints for relationships and application policy for decisions

The physical design must preserve organization and project ownership through explicit foreign keys and uniqueness constraints. A relationship referring to a project-owned object must establish that the referenced object belongs to the same project, not merely that some row with that ID exists.

For example, a group-membership relationship for Support must reference both a group in Support and the principal's Support membership. A resource grant for Support must not refer to a Deployment in Finance. A document allowlist must not point to a group in another project. Apply equivalent constraints as the owning resource tables are introduced; do not invent placeholder Deployments or Documents to satisfy a future foreign key in issue #24.

[PostgreSQL's foreign-key documentation](https://www.postgresql.org/docs/18/ddl-constraints.html#DDL-CONSTRAINTS-FK) supports referencing a group of columns. Including project identity with the referenced object's identity is the selected way to preserve these scope relationships. Use the accepted target-specific grant tables with real foreign keys. Do not substitute a generic resource registry or add unrelated domain tables merely to create future grant targets.

Use uniqueness to prevent ambiguous identity mappings and duplicate membership/manager relationships. Each target-specific grant table must enforce the accepted unique recipient/action/target assignment. Remove revoked assignments from current grant tables and retain their audit history separately so that removal followed by readmission cannot revive old access accidentally. Additional keys, indexes, deletion actions, and audit schema still need a review against the owning lifecycle rules.

Foreign keys do not prove that the current caller may grant a permission, that a human is unsuspended, or that another active grantor will remain. Those are application decisions that must be coordinated with the write transaction and concurrent changes. PostgreSQL explicitly cautions against using a row CHECK constraint to enforce conditions involving other rows. Use the appropriate scoped constraints, current policy checks, and transactional concurrency controls for each invariant; neither layer replaces the other.

#### Trace Alice and SupportBot through the model

This is an illustrative authorized state, not a provisioning template that silently grants rights:

- The installation organization contains the **Support** project.
- **Alice** is a human principal; **SupportBot** is a separate application principal owned by Support.
- Both have Support project membership.
- **Support documents** is a group in Support. Alice and SupportBot are group members; Alice also has a separate manager assignment. Her manager assignment is not the reason she passes ordinary document-reading checks.
- Deployment A and Deployment B are resources in Support. The example assumes no other grants on B and no access to an HR-only document group.

| Recipient  | Action          | Target       | Grant level       |
| ---------- | --------------- | ------------ | ----------------- |
| Alice      | Manage releases | Deployment A | Can use and grant |
| Alice      | Query           | Deployment A | Can use and grant |
| SupportBot | Query           | Deployment A | Can use           |

For a query to A, credential verification identifies SupportBot and checks the key's validity and binding. The application policy then checks current account status, Support membership, Query on A, and document access through SupportBot's current group relationships and the documents' stored allowlists. It does not use Alice's permissions simply because Alice is the person asking through the bot.

SupportBot can query A using permitted evidence but cannot release A, administer grants, or read an HR-only document. Neither example principal gains release authority on B from these assignments. Removing SupportBot's Query grant blocks querying A even though its key and project membership remain valid. Removing its Support-documents membership removes that document access even if Query remains. Replacing its key changes neither relationship.

If Alice creates a new Deployment, the accepted creation transaction records that Deployment, its first ready serving version, and her explicit initial grants together. Thereafter the same ordinary records authorize her releases; a stored creator ID cannot override a later authorized removal of her permissions.

#### Preserve the model across requests and lifecycle changes

The application-owned access context carries the verified actor and relevant scope/verification information. It is not the Principal database row, an ORM session, a Kratos response, or an authoritative permissions document supplied by the client. The optional delegated-subject boundary remains reserved; v1 integrations have no subject, and unsupported delegation assertions are rejected.

Read current authority through Access's shared application boundary. A login or successful key verification is not a permanent permission snapshot. Request-local representations must not bypass the existing rechecks before protected content is used/disclosed or before queued work publishes. HTTP, MCP, and workers reuse the policy through application contracts rather than implementing separate permission rules in each adapter.

| Change | Required effect on the records and effective authority |
| --- | --- |
| Human suspension | Preserve recorded grants and relationships, but prevent the principal from acting. Last-manager/grantor status cannot block emergency suspension. |
| Ordinary project removal | Clear that human's own project grants, group memberships, and manager assignments under the handover rules. Grants they previously made to others remain. Readmission starts without restored old rights. |
| Grant downgrade or removal | Change authority for that recipient/action/scope; preserve ordinary last-grantor handover. Attribution does not override the new state. |
| Application permission change | All valid keys use the application's updated authority. No key rotation or per-key permission copy is required. |
| Key revocation | Stop use of that key without deleting the account or its grants. Other valid keys still follow current account permissions. |
| Application-account deletion | Retire the principal, revoke keys, and remove its access and application-specific administration grants under section 11. Project-owned data and retained historical attribution follow their separate lifecycle rules. |

Group and whole-project deletion retain section 11's distinct dependency, scope, and handover exceptions. The shared record model does not replace those rules with blanket cascading deletes.

#### Alternatives, delivery scope, and remaining schema choices

**Separate human and application permission systems were rejected.** Their authentication differs, but their project, action, and document checks share the same model. Separate systems would duplicate those rules and invite divergent behavior. Human-only restrictions remain explicit in the common policy.

**An authoritative per-account JSON permissions document was rejected.** It makes the individual assignments and their database-enforced relationships harder to maintain. Individual rows support scoped changes and references. This choice does not prohibit JSON in unrelated payloads or safe read representations.

Issue #24 establishes stable principals, the shared verified-context and permission contracts, the access records and scoped constraints needed for those contracts, and focused behavior/integration tests. Section 11's issue boundaries still apply: Kratos integration is #25; provisioning is #27; administration workflows are #28; bulk document/evidence enforcement is #29; and incoming credentials are #30. Later domain issues introduce their own real resources and integrate the agreed resource-grant rules. The illustrative Deployment and document examples do not authorize implementing those domains here.

Section 13 provides the complete Access foundation table map, including common versus kind-specific information, keys, relationships, audit fields, deletion behavior, and concurrency controls. The target-specific layout, current-state/history separation, unique recipient/action/target assignment, `can_grant` boolean, and fixed code-owned action catalogue are accepted. The subsequent review also accepted the small application-account extension with enforced project binding and project-scoped coordination of Access writes with scope revisions. Remaining column/type details, indexes, and event-specific audit fields are implementation proposals; no SQL migration or ORM model has been implemented or verified by this design discussion.

During delivery, verify product behavior rather than adding architecture/import-boundary tests. Focus issue #24 tests on stable identity, human/application policy differences, membership versus action permission, exact scope, non-enumerating denials, unsupported-subject rejection, and database rejection of cross-project relationships. Keep the separation from document scope explicit; issue #29 supplies the full bulk evidence checks. As the owning workflows arrive, also exercise revocation, handover races, creator grants, and credential changes against this same model. These are required validation targets, not claims of tests already implemented or passed.

### 13. Proposed Access foundation table map

**Status: application-account extension and write-coordination approach accepted on 24 September 2026; remaining physical details proposed.** Section 12 records the previously accepted storage decisions. The developer subsequently accepted both recommendations from this table-map review:

1. Keep the small `application_accounts` extension, sharing the principal ID and permission model, with its one owning project enforced in membership relationships.
2. Coordinate Access writes through short project-scoped transactions, the organization/project row-lock protocol below, and scope revisions that reject stale administration changes. Narrower per-resource coordination is deferred unless measured contention warrants it.

The table map records these choices and their implementation implications. Remaining column names/types, exact action identifiers, index selection, and event-specific audit details still need implementation review; the design is not implemented or verified behavior. It covers the Access foundation and identifies later integration tables, not the complete database schema for every Epic 2 workflow or every Inframeld domain.

The proposal has **14 foundation tables**. Most are small relationship tables. They belong to one Access module in one PostgreSQL database, not 14 services, repositories, or domain aggregates. Tables for keys, Documents, Pipelines, and Deployments arrive with their owning features.

#### Column conventions

- Use stable UUID entity IDs, PostgreSQL `timestamptz` for instants, and required boolean `can_grant` on grants. Display names are labels, never permission keys. Do not impose global display-name uniqueness or infer membership from names.
- Use required, immutable organization/project ownership on live records. Every column forming a current membership, target, or recipient foreign key is non-null unless an explicit conditional relationship below says otherwise. Add the listed composite unique keys so scoped foreign keys have real referenced keys.
- Store principal kind as a constrained `human`/`application` value. A repeated kind column used for a constraint must participate in a foreign key to the authoritative kind; it is not a caller-controlled copy. Kind changes are unsupported.
- Proposed status labels are `active`, `suspended`, and `retired` for principals, and `active`/`deleting` for projects. They represent accepted lifecycle differences, not new suspension, restoration, or removal endpoints. Implement only the transitions authorized for each principal kind. An application's retirement is terminal; a retained row never makes its keys usable.
- Current assignments carry `assigned_at` and nullable `assigned_by_principal_id`. The latter is provenance, not an authorization dependency; reference the stable principal with no cascading deletion and allow it to become null under authorized erasure. Operator/bootstrap changes are identified explicitly in audit. A null value never means an ordinary caller may omit verified attribution.
- Use scope revisions on organizations and projects, represented here by a nonnegative integer `access_revision`. Increment the appropriate scope's revision for each committed Access administration change. The accepted purpose is to reject stale administration requests in #28, including remove-and-regrant changes; it is not a cached permission snapshot. Ordinary project changes do not increment every other project's revision. The exact request/response representation belongs to the administration contract.

#### Identity, ownership, and membership tables

In the tables below, **PK** means the primary key identifying a row; **unique** means a duplicate is rejected; **FK** means a database-enforced reference. Additional timestamps or presentation fields may be added when their owning workflow needs them.

| Proposed table | Core columns and keys | Required relationships and meaning |
| --- | --- | --- |
| `organizations` | `id` PK, `name`, `access_revision`, `created_at`. | One installation organization is provisioned in v1. No multi-organization administration follows from having this table. |
| `principals` | `id` PK, `organization_id`, `kind`, `status`, `display_name`, `created_at`; unique `(organization_id, id)` and `(organization_id, id, kind)`. | FK to organization. Stable identity shared by human and application authorization. A local admitted human is represented here; an unverified login or pending invitation does not create an active principal. Status is checked whenever authority is evaluated. |
| `human_identity_links` | `(authority, subject)` PK, `organization_id`, `principal_id`, `principal_kind` fixed to `human`, `linked_at`. | FK `(organization_id, principal_id, principal_kind)` to principal. The verified identity pair maps to exactly one local human. The link uses the verified Kratos identity source/ID; no email-based merging. This shape does not enable self-service identity linking. |
| `projects` | `id` PK, `organization_id`, `name`, `status`, `access_revision`, `created_at`; unique `(organization_id, id)`. | FK to organization. Deletion first marks the project unavailable and starts the accepted cleanup lifecycle. No stored creator or owner field supplies implicit authority. |
| `application_accounts` | `principal_id` PK, `organization_id`, `project_id`, `principal_kind` fixed to `application`; unique `(project_id, principal_id)`. | FK `(organization_id, principal_id, principal_kind)` to principal and `(organization_id, project_id)` to project. Records the application's one immutable owning project. Its ID is the shared principal ID, not a second identity. Contains no permissions or credential secret. |
| `project_memberships` | `(project_id, principal_id)` PK; `organization_id`, `principal_kind`, nullable `application_principal_id`, assignment attribution; unique `(project_id, principal_id, principal_kind)`. | FK `(organization_id, project_id)` to project and `(organization_id, principal_id, principal_kind)` to principal. The conditional application FK described below prevents admitting a bot to another project. Membership gives no operational or document permission. |
| `access_groups` | `id` PK, `project_id`, `name`, `created_at`; unique `(project_id, id)`. | FK to project. A document audience; no nested groups or role bundle. Management is recorded separately. |
| `group_memberships` | `(project_id, group_id, principal_id)` PK, assignment attribution. | FK `(project_id, group_id)` to group and `(project_id, principal_id)` to project membership. This is the principal's group-based document audience, not an operational grant. |
| `group_managers` | `(project_id, group_id, principal_id)` PK, `principal_kind` fixed to `human`, assignment attribution. | FK `(project_id, group_id)` to group and `(project_id, principal_id, principal_kind)` to project membership. A manager need not be an ordinary member; management alone is no read bypass. |

**One application, one project:** a membership row for a human must have null `application_principal_id`; one for an application must have a non-null `application_principal_id` equal to its `principal_id`. Enforce that with a row check, and add FK `(project_id, application_principal_id)` to `application_accounts(project_id, principal_id)`. The deliberate repeated ID lets PostgreSQL enforce the conditional relationship while humans retain ordinary membership in several projects. It is not a second application identifier. A nullable FK without the kind/nullability check would leave a hole.

Create an application principal, its account record, project membership, creator administration grants, and audit in one transaction. An application is eligible only while its current principal, account, project, and membership satisfy policy. Keeping the account's project reference independent of current membership permits retaining an inert account reference while removing membership during retirement. Neither retained metadata nor an orphaned incomplete identity authorizes use.

**Alternative considered; not selected:** store the application's owning-project field directly on `principals`. It saves one table but mixes application-specific ownership into every human row and still needs conditional membership constraints. The accepted small `application_accounts` extension keeps a single identity and permission model while giving application administration and credentials a clear target. A separate human-profile table is unnecessary until real human-only application data requires it; Kratos still owns passwords and sessions.

#### Current action-grant tables

Every grant row has `recipient_principal_id`, `recipient_kind`, `action`, `can_grant`, and assignment attribution. `action` is a stable code-owned identifier, not arbitrary executable policy. Use a row check for allowed action identifiers and recipient kinds in each table as the supported catalogue is implemented. Application rows must have `can_grant = false`; the recipient-kind foreign key prevents pretending an application is human. Deny unknown or unsupported actions in application policy even if persistence contains a value it cannot interpret.

The unique recipient/action/target tuple is the proposed primary key; a separate grant ID is unnecessary here. Scope revisions detect stale changes, including a deleted assignment recreated with the same tuple. A retry or duplicate request must still follow #26/#28 idempotency and conflict semantics, not silently overwrite a grant with an unconditional upsert.

| Proposed table | Primary key / exact assignment | Required foreign keys |
| --- | --- | --- |
| `organization_action_grants` | `(organization_id, recipient_principal_id, action)`. | `(organization_id, recipient_principal_id, recipient_kind)` to principal. Currently accepted installation actions are human-only; constrain the kind accordingly. No artificial project is needed. |
| `project_action_grants` | `(project_id, recipient_principal_id, action)`. | `(project_id, recipient_principal_id, recipient_kind)` to project membership, plus project target. Enforce the catalogue's human-only administration restrictions. |
| `group_action_grants` | `(project_id, group_id, recipient_principal_id, action)`. | `(project_id, group_id)` to group and `(project_id, recipient_principal_id, recipient_kind)` to project membership. Supports the accepted Add/Update/Delete documents permissions on groups. Ordinary group membership remains a separate fact. |
| `application_action_grants` | `(project_id, application_principal_id, recipient_principal_id, action)`. | `(project_id, application_principal_id)` to application account and `(project_id, recipient_principal_id, recipient_kind)` to project membership. Recipient kind is human. These are Issue keys, Revoke keys, and Delete application account permissions **over the application**, not the permissions the bot uses. |

For example, Alice's permission to issue SupportBot's keys belongs in `application_action_grants`. SupportBot's permission to query Deployment A belongs in the future `deployment_action_grants`. SupportBot's access to the Support-documents audience belongs in `group_memberships`. These three records have different purposes.

#### Audit table

The four grant tables plus the nine identity/membership tables and this audit table make the 14-table foundation.

| Proposed table | Core fields | Boundary |
| --- | --- | --- |
| `access_audit_events` | `id` PK; `occurred_at`; `organization_id`; nullable `project_id`; `actor_kind`; nullable `actor_principal_id`; narrow operator/bootstrap actor reference where applicable; affected principal ID where applicable; `event_type`; target kind and stable ID; action where applicable; relevant before/after values; reason when required; request/operation correlation when available. | A bounded historical record of an Access change. Write it in the same transaction as the state change. Normal APIs cannot edit history, but authorized retention/erasure still applies. It is never queried to grant access. |

Audit fields record historical identity/scope facts; do not make them cascading foreign keys to current grants, memberships, groups, or resources. Otherwise revocation or cleanup could erase its own history or become impossible. A target-kind/ID pair is appropriate for history because it is not an authoritative permission reference. Validate events when writing; use a bounded event payload for the relevant safe before/after values, not entire domain objects, permission snapshots, document text, keys, hashes, or session data. Do not require a fake human principal for privileged operator/bootstrap activity. The authenticated maintenance path must establish its actor reference and required reason.

This proposes the record shape, not new audit-reading rights or a permanent-retention promise. The permitted viewers, event-specific required fields, payload bounds, and retention settings must be specified with their workflows under ADR-0014 before exposing an audit API. Assignment attribution and surviving audit records do not retain unnecessary personal data indefinitely.

#### Tables integrated with later features

These are named integration points, **not additional issue #24 placeholders**. The owning feature supplies its real resource table, lifecycle, exact columns, and migration. Access continues to own grant policy and grant records; a database foreign key across owners does not make Access own the resource.

| Later table / relationship | Proposed key and references | Delivery boundary |
| --- | --- | --- |
| `pipeline_action_grants` | `(project_id, pipeline_id, recipient_principal_id, action)` PK; scoped FK to real Pipeline and recipient project membership; the common grant fields/checks. | With the Pipeline feature. Build and its other settled actions use the fixed catalogue. |
| `deployment_action_grants` | `(project_id, deployment_id, recipient_principal_id, action)` PK; scoped FK to real Deployment and recipient project membership; the common grant fields/checks. | With Deployments/Releases. Query, Manage releases, configuration, and Delete stay separate under section 11. |
| `application_credentials` | Stable credential ID; `(project_id, application_principal_id)` FK to application account; stored verifier and safe metadata, expiry/revocation, audience and the required binding. | #30. No per-key permission rows. Enforce the two-usable-key limit transactionally; credential format, verifier construction, lifetimes, and binding columns need that feature's design. |
| Document/group allowlist join | `(project_id, document_id, group_id)` unique; scoped FKs to real Document and access group. | Knowledge with #29 enforcement. The current nonempty allowlist belongs to the logical Document and protects all its versions; no per-version access copy. |
| Project upload-default/group join | `(project_id, group_id)` unique; scoped FK to project/group, with the owning default configuration and revision. | Default provisioning/configuration under ADR-0019 and its authorized update workflow. Applies to future admissions; not an automatic change to existing Documents. |
| Active upload and source-configuration group references | Scoped FKs from their real configuration/intent records to each group they currently reference. | Owning Knowledge workflows. These references must block deletion of an in-use group. Historical snapshots need their separate retention treatment. Source-administration permission details remain an explicit open policy question. |

Provisioning completion/retry state, admission/invitation records, idempotency reservations, and cleanup jobs must be designed with #25–#28 and the shared job/idempotency contract where needed. They are not missing permission tables or a reason to duplicate Kratos's credentials/sessions. This map does not claim those future workflow records have already been specified.

#### Deletion and retention behavior

Default live relationship FKs to **restrict parent deletion**. The authorized application transaction checks handover, records the change, and removes affected current rows explicitly before removing membership or a deletable group. This makes the cleanup set and audit visible in the use case. Do not use a database cascade as the implementation of an authorization workflow. Broader project/data cleanup remains the existing tombstone-and-resume process.

| Change | Required persistence effect |
| --- | --- |
| Suspend a human | Change principal status; preserve memberships/managers/grants. Bypass the ordinary last-manager/grantor handover requirement, not the audit or status checks. |
| Remove a human from a project | After handover checks, remove that recipient's project/group/application/resource grants, group memberships and manager assignments, then project membership; audit together. Do not delete grants merely because this human assigned them. |
| Revoke or downgrade a grant | Delete the current row or update `can_grant`; bump the scope revision and audit together. A later regrant is a fresh assignment with fresh attribution. |
| Delete an unused group | Check all current Document, active-upload, default and source references, then remove its own memberships/managers/grants and the group. Reference FKs prevent dangling or cross-project relationships. A default group must be replaced through its authorized configuration workflow first. |
| Delete an application | Retire its principal, revoke keys, remove its received grants/group relationships/project membership and human grants targeting the account. Retain only the inert identity/account/credential metadata justified by retention, then purge in dependency order. Do not delete project data it created. |
| Delete a project | First make the project unavailable to new work, stop its applications and revoke their keys, then clean up project data and access records under the accepted deletion lifecycle. No handover is needed for a scope being deleted. Historical audit is handled by retention, not by a blanket project cascade. |

#### Accepted write coordination and proposed indexes

Database keys prevent duplicate and mismatched relationships. They do not decide whether Alice may grant a permission or guarantee that Bob remains an active manager while Alice leaves. A row check cannot safely express a count of other eligible managers. [PostgreSQL's constraint documentation](https://www.postgresql.org/docs/18/ddl-constraints.html) explains these limits and the composite-FK mechanisms used above.

The accepted initial approach uses short **project-scoped serialization of Access writes**: acquire a shared row lock on the installation organization, then an exclusive row lock on the affected project, re-read current authority and handover conditions, check the submitted scope revision where required, apply the change, increment the revision, and write audit before committing. Installation permission/status changes acquire an exclusive organization-row lock instead. This coordinates suspension with project administration without acquiring locks for every possible remaining manager. All participating paths must use this protocol, including provisioning, maintenance recovery, later resource grant changes, credential issuance, and deletion; an optional lock in only one endpoint is insufficient.

Different projects can make ordinary Access changes concurrently. Same-project Access writes wait for one another. Plain permission reads do not acquire these exclusive administration locks. Never hold a transaction while waiting for a user, uploading data, calling Kratos, or invoking a model. Work requiring several project locks takes them in stable ID order after the organization lock; bound waits and handle transaction failure. The operation-specific commit/disclosure rules still apply outside this administration protocol. [PostgreSQL's row-lock documentation](https://www.postgresql.org/docs/18/explicit-locking.html#LOCKING-ROWS) describes the lock behavior; the accepted application protocol still needs implementation and behavioral concurrency tests. PostgreSQL does not supply these permission rules automatically.

Key issuance must read the application's full current permissions and the issuer's authority under the same project guard used by permission changes. At issuance commit, count keys still unexpired and non-revoked and insert only if a slot remains. Deletion and revocation use the compatible guard and current status checks. Group-reference creation/removal and group deletion likewise need the shared protocol at their short database commit, in addition to scoped FKs. Future workflows must integrate these guards rather than claim that a key, revision, or foreign key alone solves their race.

**Alternatives considered; deferred:** lock individual groups, applications, and resource authority sets from the start, or use serializable transactions with retries. Both are viable but require more coordination across handover, project removal, status changes, and issuance checks. Start with the accepted project guard, test the actual races, and narrow contention only if measured administration throughput requires it. This is not a promised capacity limit or a reason to serialize document processing/model calls.

Start with indexes provided by primary/unique keys, then add the paths required by policy reads: projects by member; group memberships/managers by `(project_id, principal_id, group_id)`; resource/group/application grants by `(project_id, recipient_principal_id, target_id, action)`; grantor lookup by exact target/action and `can_grant`; and audit by scope/time/ID. Reuse an existing index when its leading columns already serve the query; do not create duplicates. Index relevant referencing FK columns for cleanup. Validate actual query plans and representative data before adding permission caches or declaring a scale guarantee.

#### Review and issue #24 boundary

The proposed foundation implements stable identity, explicit ownership, memberships, managers, the four current grant target types, and audit support. #24 should introduce only the records and persistence paths exercised by its shared policy and scoped-constraint tests; it does not deliver every administration endpoint merely because their future table is mapped. Human session integration remains #25; provisioning #27; administration/handover/revision workflows #28; bulk evidence checks #29; and credential lifecycle #30. Pipeline/Deployment tables and their grants arrive with those features.

The two consequential physical choices from this review are now accepted: **the small application-account extension with enforced project binding** and **the project-scoped write guard with scope revisions**. Field spelling and ordinary index tuning do not need another round of product-policy decisions. The next issue #24 work is to map these decisions to application-owned contracts, concrete persistence constraints, and an ordered behavioral test plan, keeping later administration and credential workflows in their owning issues. Before migration implementation, settle exact action identifiers and status-transition checks against the accepted catalogue and lifecycles. Verify rejected cross-project/human-only assignments, live permission changes, no stale access after removal/readmission, and the relevant concurrency failures. This document is design evidence; none of those tests or guarantees is claimed to exist yet. Accepting the design does not authorize application-code or migration edits.

## Consequences

### Positive

- **Login and document access remain independent.** Application permissions can change while a session remains valid, and revocation also protects historical content. Human sessions, service credentials, and any future OAuth credentials use the same application policy.
- **Secure OSS operation does not require a cloud identity account or Hydra.** Local login, deployment-level external sign-in, scoped integration access, and the basic administration needed for document allowlists remain available in OSS.
- **Identity boundaries leave room for later changes without pretending those features exist today.** Stable local IDs and separate actor/subject fields preserve useful integration boundaries for future migration and delegation. Private starter defaults avoid manual access setup without automatically sharing documents.

### Negative

- **Kratos does not remove account-integration work.** Inframeld still needs account screens, flow/error handling, CSRF protection, secure bootstrap, email configuration, private administration, and deployment tests.
- **Fixed integrations cannot preserve each employee's individual permissions.** Every request uses the integration's authority. Applications requiring verified per-user access cannot treat a supplied user ID or hidden UI control as a substitute for delegation.
- **Inframeld remains responsible for current authorization everywhere.** Project grants, document allowlists, credential expiry/revocation, evidence access, and worker permission checks must remain consistent across the supported interfaces. A valid session or token is not a shortcut around them.

## Alternatives considered

The source names previously considered products and approaches that are excluded or deferred. It does not record a comparative product assessment or additional reasons for the earlier product selection.

### Use Keycloak or ZITADEL instead of Kratos

**Previously considered; not selected.** Kratos is the chosen identity technology. These products are not deployment alternatives under this decision.

### Deploy Hydra for external company sign-in

**Not required.** Kratos acts as the client of the configured external OIDC provider and establishes its own session. Issuing Inframeld OAuth tokens is a separate responsibility.

Hydra deployment and its login/consent and token-lifecycle work are deferred until an actual issuer or delegated-client requirement needs them.

### Add Auth.js, another JWT session service, or browser-local-storage bearer tokens

**Not part of the selected integration.** Studio uses Kratos's native browser flow, secure HTTP-only session cookie, and supported CSRF handling. Auth.js and an additional JWT-issuing service are unnecessary for that design. Native-app tokens are not repurposed as browser cookies.

### Grant access from external claims or caller-supplied user identities

**Ruled out.** Successful company login does not confer administrator privileges. Equal email addresses do not authorize account merging. External groups need an explicitly designed synchronization policy before they affect membership.

Likewise, a supplied user ID, group name, or canary affinity value cannot expand an integration's document access. Verified delegation is deferred rather than approximated with untrusted identity fields.

### Introduce a general authorization engine or policy language now

**Not selected.** The initial policy uses application-owned project membership, resource-specific action grants, bounded grant authority, and document group allowlists. No external relationship engine, general policy language, deny hierarchy, or per-chunk policy is required.

The 24 September 2026 review reconsidered OpenFGA and an embedded authorization library after the detailed administration and data-model decisions. The accepted course remains **the product-specific Access module with PostgreSQL**. The number of documented edge cases does not itself require a general authorization engine: the chosen relationships remain explicit and bounded, without nested groups, arbitrary inheritance, or a custom role designer.

OpenFGA is technically capable of expressing direct and group-based permissions; rejecting it for v1 is a scope and operational tradeoff, not a claim that it cannot represent this model. It normally adds a separate authorization service, its datastore migrations, and production configuration. Its stronger-consistency reads support fresh permission checks, while coordination between application state and authorization writes still needs integration design. See the official [modeling guides](https://openfga.dev/docs/modeling), [Docker setup](https://openfga.dev/docs/getting-started/setup-openfga/docker), [source-of-truth guidance](https://openfga.dev/docs/best-practices/source-of-truth), and [consistency controls](https://openfga.dev/docs/interacting/consistency).

The difficult product workflows remain Inframeld's responsibility: preserving a last manager/grantor during ordinary changes, checking all application permissions when issuing a key, and creating a Deployment with its initial authority. An engine can evaluate component permission checks, but it does not implement these workflows or automatically protect their concurrent state changes. Keeping the relevant application records and grants in PostgreSQL allows their checks and writes to be coordinated within an application transaction.

An embedded library such as PyCasbin avoids another service, but still introduces a policy model and persistence integration; loaded policy across multiple processes needs synchronization. It is not selected for v1 because this review found no demonstrated simplification over the fixed product policy. The official [Casbin overview](https://casbin.apache.org/docs/overview/) and [watcher documentation](https://casbin.apache.org/docs/watchers/) describe those capabilities. This decision does not exclude ordinary supporting libraries or justify implementing a generic policy engine inside Access.

Production qualification remains necessary: shared deny-by-default enforcement, scoped database constraints, transactional permission changes, and behavior tests for isolation, escalation, revocation, and concurrent administration. Use indexed scoped queries and bulk document checks, and measure representative workloads before adding authorization caching. No throughput or capacity guarantee follows merely from this choice.

Reconsider a dedicated engine if actual requirements introduce deep permission inheritance, independently deployed applications sharing one authorization model, or measured workloads that justify the integration and operational cost. More users, documents, or named actions alone do not select an engine. Keep the current application boundary clear so a future change can be evaluated; do not build speculative engine adapters now. Section 12 records the separately accepted target-specific grant tables and separation of current grants from audit history.

Resource-specific Pipeline/Deployment permissions are accepted in Section 11. Finer document ACL behavior beyond group allowlists remains future work. Keeping the document policy separate from authentication preserves that boundary without implementing a larger framework now.

## References

| Reference | Responsibility |
| --- | --- |
| [Canonical architecture guide](../ARCHITECTURE.md) | Overall architecture, document filtering, and in-flight authorization trade-offs. |
| [ADR-0001](ADR-0001-modular-application-structure.md) | Module ownership and application/infrastructure boundaries. |
| [ADR-0002](ADR-0002-product-owned-openapi-contract.md) | Public API contract and client integration. |
| [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md) | Durable operations, idempotency, and show-once credential issuance. |
| [ADR-0011](ADR-0011-hosted-vercel-and-aws-deployment-profile.md) | Deployment profile. |
| [ADR-0017](ADR-0017-answer-feedback.md) | Answer-feedback permissions and API contract. |
| [ADR-0018](ADR-0018-first-party-mcp-adapter.md) | MCP's fixed-authority client profile and qualification. |
| [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) | Private starter provisioning and reversible publication modes. |

The Ory documentation, source, release, and licensing links are retained beside the relevant integration and recorded-evidence sections. Section 11 owns the accepted bounded-administration decisions, supporting security references, and remaining matrix/recovery questions. Credential-lifetime/issuance details, future delegation protocol, broader organization administration, and EE packaging remain unresolved or outside this decision as specified above.
