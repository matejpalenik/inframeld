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

1. Identify the credential family, action and exact target. Introduce relationships through Alice or SupportBot.
2. Follow verification, local identity resolution and current authorization in order. Explain visibility and failures at their owning boundaries.
3. For changes or retries, trace admission, commit, dispatch and disclosure as applicable.
4. Inspect code before claiming implementation. Separate accepted contracts, inspected behavior, recorded evidence and unfinished qualification.
5. Cite the precise rule and report unresolved contradictions. Loading this skill authorizes no edits, grants, credential issuance, deployment or paid calls.

Before domain-specific backend component design, code generation or structural review, read [this module's architecture](references/architecture.md) and the relevant workflow, together with Coding Standards. Its accepted design, inspected implementation and proposals have different status. Resolve a pending architectural choice before suggesting code that depends on it. Behaviour-only questions can go directly to their workflow.

## Read as needed

- For module responsibilities, collaborators, data ownership or component design/review, read [Architecture](references/architecture.md).

- For cookie verification, credential dispatch, evidence or CSRF, read [Browser sessions](references/browser-sessions.md).
- For human login, consent, refresh or credential versions, read [Human CLI login](references/human-cli-login.md).
- For issuance, verification, overlap or lost-secret recovery, read [Application keys](references/application-keys.md).
- For eligibility, grants, audiences, invitations or maintenance authority, read [Authorization](references/authorization.md).
- For cleanup, completion and provider races, read [Recovery](references/recovery.md).
- For connection management, encryption or budget authority, read [Model connections and provider credentials](references/model-connections-and-provider-credentials.md).

The [Access guide](../../../docs/development/access-control.md) owns behavior, [Access contracts](../../../docs/development/access-contracts.md) owns exact mappings and delivery drafts, and the [data model](../../../docs/development/data-model.md#access) owns records. The references explain these sources without replacing them.
