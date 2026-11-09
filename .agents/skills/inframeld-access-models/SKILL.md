---
name: inframeld-access-models
description: Explains and reviews Inframeld identity, authentication, permissions and credential protection. Use for browser sessions, human CLI OAuth, application keys, grants, recovery or provider-secret boundaries, not generic authentication tutorials.
---

# Inframeld Access

Help a developer understand who is calling and what that caller may do now. Access owns local principals, admission, memberships, action grants and document-access rules. Kratos verifies human identity. Hydra supplies human CLI OAuth credentials. ModelGateway owns outbound model dispatch, separate from incoming authentication.

## Working model

A principal is a stable local identity. Alice's browser and human CLI resolve to the same human principal. SupportBot has a separate application principal. An application key identifies SupportBot even if Alice used the CLI to issue it.

| Path | Incoming credential | Identity checks |
| --- | --- | --- |
| Browser | Kratos session cookie | Current verified human session and local eligibility. |
| Human CLI | Hydra access token | Private token verification, current Kratos eligibility and the same local human. |
| Application | Inframeld application key | Full key verification and the account's current state and permissions. |

These are accepted paths, not a claim that all lifecycle work is complete. OAuth lets the CLI obtain tokens after browser sign-in instead of collecting Alice's password. OpenID Connect (OIDC) adds identity information to that flow. Consent approves requested CLI access. It neither creates local product admission nor grants project permissions.

Suppose SupportBot has Query on Production and membership in SupportKnowledge. Removing Query prevents that action. Removing membership changes readable evidence. Replacing a key changes neither grant. Project membership, action authority, document reading and group management are separate relationships.

## Essential rules

- Select one credential family and reject malformed or competing credentials before provider I/O. Never try another family after failure.
- Product access needs current account, membership and credential validity plus exact operation authority. Authenticate and authorize before protected work or replay.
- Authentication context carries actor identity and complete non-secret evidence, not status or permissions. Current authorization interprets it separately.
- Human-only administration and bounded delegation remain explicit. A manager also needs ordinary membership in the same group. Empty document allowlists are never public.
- Recovery blocks and permanent CLI invalidation solve different problems. An older completion cannot clear a newer block. Partial cleanup is not release authority.
- Incoming application keys and outgoing provider secrets have separate purposes and lifecycles. Every remote model call uses ModelGateway and approved destinations.

## Explain or review

Trace the chosen credential, local identity, current eligibility, exact action/target and protected evidence through a concrete example. Check admission, commit, dispatch and disclosure where relevant. Inspect code before claiming implementation and cite the owning rule.

Before backend component design, code generation or structural review, read [module architecture](references/architecture.md), the affected workflow and Coding Standards. Behavior-only questions go directly to their workflow. Pending proposals do not authorize dependent code.

## Accepted decision references

These contracts were approved on 2026-10-29. Apply them without reopening their policy. Implementation and qualification remain separate.

- [PD-ACCESS-01](references/decision-key-currentness.md): Before defining the application-key verifier/authenticator contracts or implementing key-aware authorizers and protected replay.
- [PD-ACCESS-02](references/decision-admitted-work-authority.md): Before admitting, executing or resuming durable work that must interpret credential expiry, rotation, revocation or replacement.

- [PD-ACCESS-05](references/decision-provider-secret-lifecycle.md): When implementing protected provider-credential management, storage or deployment-key integration, and before claiming the complete secret boundary is qualified.

## Accepted contracts for affected work

Load the accepted contract matching the trigger. The developer resolved PD-ACCESS-06 on 2026-10-29 and PD-ACCESS-07 on 2026-10-30. Do not request the same decisions again. Native representations and qualification remain implementation work. A later policy change follows [decision finalization](../../../docs/development/guides/architecture-decisions.md).

- [PD-ACCESS-06](references/decision-setup-read-authority.md): Before defining defaults/setup read contracts or implementing HTTP/MCP/CLI prepublication status resolution.
- [PD-ACCESS-07](references/decision-human-cli-issuer-binding.md): Before changing human CLI callback registration, success/error association, issuer-response capability handling or maintained recipient-proof acquisition. Issuer-bound registration and the shared transient acquisition owner are implemented for the repair-only example and the separate [bootstrap CLI producer](references/host-maintenance.md#first-administrator-cli-proof). The [verification report](../../../docs/development/reports/recipient-proof-verification.md) records historical repair native-driver coverage. The current unmerged bootstrap candidate has passed its maintained private HTTPS/Chromium profile for real-provider proof, pristine installed-consumer claim, original replay after grant removal and competing-identity denials, with independent SQL checks. The protected browser bridge does not qualify ordinary SystemBrowser dispatch, public interactive-terminal or signal behavior. The complete saved-login lifecycle remains unfinished.

Recovery production contracts are [resolved under PD-ACCESS-03](references/decision-recovery-production-completion.md). Read its acceptance matrix when implementing trusted callbacks, durable cleanup or host continuation. Private native delivery, bounded provider execution and proof-backed completion are implemented. Protected host continuation and the narrow [Project metadata repair consumer](references/host-maintenance.md#project-metadata-authority-repair) are implemented through the backend maintenance command. The private [first-administrator bootstrap consumer](references/host-maintenance.md#first-administrator-bootstrap-consumer) is implemented. The separate #350 CLI proof producer is implemented in the current unmerged candidate, with the bounded native qualification described above. Migration 0003 already initializes the authoritative installation UUID. #27 owns usable integration of the proof producer and private consumer, using independently trusted operator inspection for the existing installation, reviewed candidate and deployment/exec bindings. It does not require a new initializer or context exporter. Private starters belong to #349 and first-answer setup to #166. The complete operator procedure, dry run and human acceptance remain unready under [#185](https://github.com/matejpalenik/inframeld/issues/185) before v1. Group repair and other action-repair variants remain design-only and unsupported. Historical repair examples and their verification report retain separate scope, with complete human repair acceptance deferred to [#298](https://github.com/matejpalenik/inframeld/issues/298). The owning handoff reference distinguishes these boundaries.

- [Restoration evidence cutover](../../../docs/adr/ADR-0127-fence-human-authentication-evidence-at-restoration.md): Before implementing deliberate restoration, version-bound browser authentication or linked-human consent checks. Read the [browser sequence and accepted late-session limit](references/browser-sessions.md#restoration-evidence-cutover). This 2026-11-05 decision is accepted, with implementation and qualification unfinished.

## Read as needed

Choose the row matching the task. Workflow, contract and architecture views are separate reading units. Do not load this whole table.

| Task | Direct reference |
| --- | --- |
| Create an additional Project or inspect own Organization permissions | [Actions and initial Project grants](references/actions-and-initial-grants.md#initial-project-grants) and [implemented creation transport](references/grant-contracts.md#ordinary-project-creation). The own-access read and atomic eighteen-grant creation are implemented. The supported account-to-API procedure and human acceptance remain unfinished under [#313](https://github.com/matejpalenik/inframeld/issues/313). |
| Project naming, metadata authority or first-grant repair | [Approved Project metadata decision](references/decision-project-metadata-authority.md), accepted on 2026-10-30. Project metadata and the narrow [authority-repair consumer](references/host-maintenance.md#project-metadata-authority-repair) are implemented. The verification report records selected repair-only native-driver coverage. The ordinary operator journey and deferred human acceptance remain unqualified. |
| Actions and initial grants | [Actions and explicit initial grants](references/actions-and-initial-grants.md) |
| Admission and invitations | [Admit humans and activate invitations](references/admission-and-invitations.md) |
| First admission, recovery and credential-state coordination | [Coordinate database steps for one identity](references/identity-admission-coordination.md), the accepted PD-ACCESS-04 resolution. |
| Application key contracts | [Application-key format and transport contracts](references/application-key-contracts.md) |
| Application identity and key lifecycle | [Application accounts and keys](references/application-keys.md) |
| Module/component design or structural review | [Access architecture: identify the caller, then check authority](references/architecture.md) |
| Permission concepts and delegation | [Current permissions and bounded administration](references/authorization.md) |
| Cookie verification and CSRF | [Browser sessions and authentication evidence](references/browser-sessions.md) |
| Evidence, credential generations and recovery facts | [Credential evidence and recovery records](references/credential-and-recovery-records.md) |
| Credential dispatch | [Choose one incoming credential](references/credential-dispatch.md) |
| Eligibility and current authority | [Current account and credential eligibility](references/eligibility-and-current-authority.md) |
| Grant administration | [Administer an exact action grant](references/grant-administration.md) |
| Grant contracts | [Exact-target grant transport contracts](references/grant-contracts.md) |
| Grant target contract | [Exact grant target variants](references/grant-target-contract.md) |
| Host maintenance | [Host-authorized bootstrap and repair](references/host-maintenance.md) |
| Human cli consent | [Approve a human CLI access request](references/human-cli-consent.md) |
| Human cli credential lifecycle | [Store, refresh and revoke a human CLI login](references/human-cli-credential-lifecycle.md) |
| Human OAuth login and local admission | [Human CLI login and consent](references/human-cli-login.md) |
| Logical identities, memberships and grant meaning | [Identity, membership and grant records](references/identity-and-grant-records.md) |
| Existing Principal/ProjectMembership and runtime IDs | [Implemented Access models](references/implemented-access-models.md) |
| Database structure, scoped constraints, grants and audit | [Access persistence](references/access-persistence.md) |
| Ordered relationship writes for demotion, departure or deletion | [Lifecycle persistence](references/access-lifecycle-persistence.md) |
| Invitation contracts | [Invitation requests, responses and restrictions](references/invitation-contracts.md) |
| Memberships groups and handover | [Memberships, groups and safe handover](references/memberships-groups-and-handover.md) |
| Model connections and provider credentials | [Model connections and provider credentials](references/model-connections-and-provider-credentials.md) |
| Private recovery handoff | [Private identity-recovery handoff](references/private-recovery-handoff.md) |
| Provider credential storage | [Protect stored provider credentials](references/provider-credential-storage.md) |
| Query and document authorization | [Authorize a question and its source evidence](references/query-and-document-authorization.md) |
| Recovery completion | [Release only the completed recovery obligation](references/recovery-completion.md) |
| Recovery provider cleanup | [Confirm provider cleanup without guessing](references/recovery-provider-cleanup.md) |
| Recovery purpose, independent blocks and boundaries | [Recovery blocks, cleanup and completion](references/recovery.md) |
| Session contracts | [Human and application session contracts](references/session-contracts.md) |

## Source ownership

Focused references own accepted behavior and logical design. Code, generated OpenAPI and migrations own implemented representations. Read exact definitions when fields matter, ADRs for rationale or conflicts, and matching pending decisions before dependent design. Human guides own development procedures.
