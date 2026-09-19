# ADR-0005: Kratos identity and application-owned authorization

**Status:** Accepted — identity, authorization boundaries, and private starter/access defaults.  
**Date:** 17 September 2026.  
**Revised:** 19 September 2026.  
**Source:** [Canonical architecture guide](../ARCHITECTURE.md).  
**Related:** [Application structure](ADR-0001-modular-application-structure.md), [API contract](ADR-0002-product-owned-openapi-contract.md), [durable jobs and idempotency](ADR-0007-durable-jobs-idempotency-and-recovery.md), [deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md).

## Context

Inframeld has two main kinds of callers: engineers using its web console, **Studio**, and customer applications asking questions through its API. Optional service automation can also build, evaluate, or release pipeline versions when explicitly permitted.

Every protected operation needs to answer two separate questions:

| Question                          | Responsibility                                                                           |
| --------------------------------- | ---------------------------------------------------------------------------------------- |
| **Who is calling?**               | **Authentication:** verify a human session or an application credential.                 |
| **What may this caller do here?** | **Authorization:** check the caller's current project, action, and document permissions. |

A successful login answers only the first question. Alice can have a valid session without access to the Finance project. Removing her Finance membership must remove that access even while her login remains valid.

The same separation applies to customer applications. Recognizing SupportBot's credential does not authorize every document or let the application claim another user's rights.

We need this behavior in both local and production installations, without requiring a cloud identity account. The design must also distinguish signing in through a company's identity provider from operating an OAuth server, and application-level access from future verified access on behalf of individual users.

## Decision

**Ory Kratos owns human identity and sessions. Inframeld owns its account-screen integration and all application authorization. Customer applications use scoped, expiring, revocable opaque credentials.**

The initial document policy uses group allowlists. Integrations act with their own fixed application permissions; verified end-user delegation and Hydra deployment are deferred.

### 1. Keep four identity and access responsibilities separate

An **identity provider** authenticates users. **OpenID Connect (OIDC)** is the sign-in protocol used here to connect to an external provider. An **OAuth issuer** is a different responsibility: issuing access tokens that other applications present when calling an API.

| Responsibility                                    | Example                                                                                           | Selected approach                                                                                                                                      |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Manage human identity and sessions**            | Alice signs in, uses multi-factor authentication (MFA), recovers her account, or logs out.        | Kratos owns credentials and sessions. Inframeld supplies the account-screen integration.                                                               |
| **Sign in through an external provider**          | Alice signs in through the company's configured OIDC provider and receives a Kratos session.      | Kratos acts as an OIDC **client**. Deployment-level configuration is included in open-source v1; Hydra is not required.                                |
| **Issue OAuth/OIDC tokens to other applications** | Inframeld issues scoped access tokens, potentially for an application acting on a user's behalf.  | Hydra is the corresponding Ory **issuer**. Its deployment, login/consent integration, and token lifecycle are deferred.                                |
| **Authenticate and authorize API clients**        | A customer application queries permitted documents, or an authorized automation builds a version. | Inframeld verifies the supported credential and applies current project, action, and document rules. This does not inherently require an OAuth server. |

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

| Scope                                                                             | Treatment                                                                                                                                                                                                      |
| --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **First-party login, project API access, and CI/CD credentials**                  | Included in OSS v1. Here CI/CD covers the application's build, evaluation, and release operations.                                                                                                             |
| **Basic access administration needed to use group allowlists safely**             | Included in OSS v1. Basic secure operation must not depend on EE.                                                                                                                                              |
| **Deployment-level external OIDC sign-in**                                        | Included in OSS v1; configured by the installation operator.                                                                                                                                                   |
| **Organization-managed federation policies and per-organization providers**       | Possible later EE packaging, not an implemented or guaranteed capability.                                                                                                                                      |
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

| Requirement                 | Behavior                                                                                                                |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| **Secret generation**       | Generate a high-entropy random secret.                                                                                  |
| **Stored representation**   | Store only a cryptographic verifier/hash, a safe identifier, and a safe display prefix—not the plaintext credential.    |
| **Lifetime**                | Credentials expire and can be revoked. Check expiry, revocation, and current scope on every request.                    |
| **Action grants**           | Select `query`, `build`, `evaluate`, and `deploy` explicitly. A query grant does not imply any of the others.           |
| **Document scope**          | A query integration has an explicit document-group **ceiling**: the maximum document-group scope its authority permits. |
| **Ordinary CI permissions** | Exclude membership administration and provider-secret access.                                                           |
| **Issuance**                | Follow the show-once secret behavior in [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md).                  |

The exact administrative roles, maximum credential lifetime, and rules for who may issue which grants still need a decision. Selecting the mechanism does not give every user permission to create credentials.

A future OAuth credential must resolve to the same application principal and policy. It must not create an alternative authorization model.

#### Example: building is not permission to promote

Support CI has `build` and `evaluate`. It can produce a pipeline version and comparison, but it cannot promote that version.

A separately authorized release job has `deploy`. It supplies the **expected deployment revision**, which protects against overwriting a concurrent change, and an **idempotency key**, which identifies a retry of the same command. It invokes the same release command as a human.

Audit records identify the service principal and the credential used. They must not invent a human actor for automated work.

### 5. Keep document authorization in one application policy

A **group allowlist** records which application groups may access a document. Group membership and document allowlists are application data in PostgreSQL.

Project access and action permission are prerequisites. A document's allowlist narrows access further; it does not grant entry to another project or permission to perform an otherwise forbidden action.

Authentication and session code remain separate from document policy. That separation allows finer permissions later without changing login or rewriting application use cases.

#### The minimum access boundary

An **access context** carries the verified actor, an optional verified delegated end-user subject, the project, and credential grants.

The **actor** is the caller whose authority has been verified. A **delegated subject** would be a separately verified user the application is permitted to represent. In v1, a human session has a human actor, and a fixed integration has an application actor with no delegated subject.

```text
Verified caller + project + credential grants
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

An administrator assigns the integration its explicit document-group scope. Inframeld also checks the integration's project membership and query permission.

There is no verified human subject in the request. The application's authority is therefore the same whether Alice or Bob is asking through it.

Suppose `SupportBot` can read `SupportKnowledge` but not `HRPrivate`:

| Request                                                                                  | Inframeld document authority                                                                                                   |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Alice asks through SupportBot.                                                           | SupportKnowledge only.                                                                                                         |
| Bob asks through SupportBot.                                                             | SupportKnowledge only.                                                                                                         |
| SupportBot supplies `userId: Alice`, an HR group name, or Alice's canary affinity value. | No additional access. Caller-supplied values cannot expand SupportBot's authority; unsupported delegation claims are rejected. |
| An administrator explicitly adds HRPrivate to SupportBot's scope.                        | Every request using SupportBot's authority can potentially reach HRPrivate.                                                    |

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

| Application ceiling            | Verified user's rights              | Effective document access                                                      |
| ------------------------------ | ----------------------------------- | ------------------------------------------------------------------------------ |
| SupportKnowledge and HRPrivate | Alice may read both.                | Both, provided project membership and the requested action are also permitted. |
| SupportKnowledge and HRPrivate | Bob may read only SupportKnowledge. | SupportKnowledge only.                                                         |
| SupportKnowledge only          | Alice may read both.                | SupportKnowledge only; her HR rights do not expand the application's ceiling.  |

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

| Operation                                                  | Required authority                                                                                                                     |
| ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| **Automatic source/configuration update**                  | The initiating actor needs the relevant source or configuration permission, plus build and deploy permissions for the explicit target. |
| **Change publication mode**                                | Deploy authority is required.                                                                                                          |
| **Enable Automatic updates and apply the selected inputs** | Build authority and valid inputs are also required.                                                                                    |

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

| Recorded observation                                                                                  | Limit of the evidence                                                                                                                        |
| ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **Kratos OSS v26.2.0 and Hydra OSS v26.2.0**, both released on **20 March 2026**, use **Apache-2.0**. | These observed versions are not automatically the qualified Inframeld images. No load test, security audit, or migration test was performed. |
| Ory documents identity/configuration import and compatible core APIs for Ory Network.                 | This describes a possible migration path, not a tested guarantee that sessions, IDs, and every feature transfer unchanged.                   |
| Paid/cloud announcements describe **v26.3.3** capabilities.                                           | They do not establish that OSS v26.2.0 includes every advertised capability. Inspect the actual pinned OSS release during implementation.    |

Recorded references: [Kratos v26.2.0](https://github.com/ory/kratos/releases/tag/v26.2.0), [Hydra v26.2.0](https://github.com/ory/hydra/releases/tag/v26.2.0), [Apache-2.0 license](https://github.com/ory/kratos/blob/v26.2.0/LICENSE), [Ory Network](https://www.ory.com/network), and [v26.3.3 announcement](https://changelog.ory.com/announcements/ory-network-ory-hydra-ory-kratos-v26-3-3-released).

A future EE offering can run the same Kratos technology in cloud infrastructure or use Ory Network. Preserve stable local IDs and rehearse identity mapping, domain changes, and reauthentication before relying on migration behavior.

Keycloak and ZITADEL were considered previously. They are not alternative deployment choices after the Kratos decision.

### 10. Verify the security boundaries before release

These are required acceptance cases, not completed tests or functionality implemented by this record.

| Area                                      | Required verification                                                                                                                                                                                                   |
| ----------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Application scope**                     | Deny commands and queries outside the caller's permissions. Apply current group membership. Reject forged user, group, and issuer assertions.                                                                           |
| **Session lifecycle**                     | Exercise local login, recovery, logout, disabled identities, required MFA, invalid/expired sessions, and an unavailable Kratos session check. Unverifiable sessions fail closed.                                        |
| **Browser and administration boundaries** | Test CSRF protection and that identity administration remains private.                                                                                                                                                  |
| **External OIDC**                         | Exercise configured sign-in, issuer and redirect validation, deliberate account linking, and upstream-provider unavailability.                                                                                          |
| **Service credentials**                   | Reject expired or revoked credentials and test lost key-creation responses against the show-once behavior.                                                                                                              |
| **Automation grants**                     | Prove that a CI principal with build/evaluate grants cannot deploy, administer membership, or access provider secrets.                                                                                                  |
| **Fixed integration authority**           | Prove that caller-supplied identity cannot expand an integration's document scope and that v1 rejects delegation claims.                                                                                                |
| **Future delegation**                     | When implemented, test actor/subject binding and both directions of the permission intersection: the user's rights cannot expand the application ceiling, and the application's rights cannot expand the user's access. |

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

### Introduce a general authorization engine or fine-grained policy system now

**Not selected.** The initial policy uses application-owned project/action checks and document group allowlists. No external relationship engine, general policy language, deny hierarchy, or per-chunk policy is required.

Finer ACL behavior remains future work. Keeping the document policy separate from authentication preserves that boundary without implementing a larger framework now.

## References

| Reference                                                        | Responsibility                                                                    |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| [Canonical architecture guide](../ARCHITECTURE.md)               | Overall architecture, document filtering, and in-flight authorization trade-offs. |
| [ADR-0001](ADR-0001-modular-application-structure.md)            | Module ownership and application/infrastructure boundaries.                       |
| [ADR-0002](ADR-0002-product-owned-openapi-contract.md)           | Public API contract and client integration.                                       |
| [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md)    | Durable operations, idempotency, and show-once credential issuance.               |
| [ADR-0011](ADR-0011-hosted-vercel-and-aws-deployment-profile.md) | Deployment profile.                                                               |
| [ADR-0017](ADR-0017-answer-feedback.md)                          | Answer-feedback permissions and API contract.                                     |
| [ADR-0018](ADR-0018-first-party-mcp-adapter.md)                  | MCP's fixed-authority client profile and qualification.                           |
| [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) | Private starter provisioning and reversible publication modes.                    |

The Ory documentation, source, release, and licensing links are retained beside the relevant integration and recorded-evidence sections. Exact administrative roles, credential-lifetime/issuance rules, future delegation protocol, broader organization administration, and EE packaging remain unresolved or outside this onboarding decision, as described above.
