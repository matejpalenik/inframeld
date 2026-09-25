---
name: inframeld-access-models
description: Explain or review Inframeld Kratos identity, organization/project grants, document-group access, fixed integrations, provider connections, model roles and persistent outbound credentials. Use for identity, permission or gateway-security boundaries, not generic authentication tutorials.
---

# Inframeld Access Models

Explain who may act, which documents they may read, and how model credentials are kept separate from incoming application keys. Access owns local principals, memberships, groups, and action policy. ModelGateway owns the outbound model boundary. Do not blend those responsibilities.

## Scope and reading route

Default to read-only guidance. Loading this skill grants no editing, grant changes, credential issuance, deployment, or paid-call authority. Resolve code paths from the repository root. Read only the sources relevant to the question, and cite the current rule. The 14-table Access foundation is created by [the initial migration](../../../apps/backend/migrations/versions/0001_initial.py). The current PostgreSQL integration test checks table presence, not every database constraint or workflow.

- For permissions, read [Access control](../../../docs/development/access-control.md); start at [bounded administration and recovery](../../../docs/development/access-control.md#section-bound-administration-grants-and-recovery) for its complete action matrix and qualifications.
- For records, read [Access in data-model.md](../../../docs/development/data-model.md#access), including the [accepted logical model](../../../docs/development/data-model.md#access) and [14-table foundation](../../../docs/development/data-model.md#proposed-access-foundation-table-map). For races, read [accepted write coordination](../../../docs/development/access-control.md#section-accepted-write-coordination-and-proposed-indexes).
- For providers, read [Model connections](../../../docs/development/model-connections.md) and [supporting records](../../../docs/development/data-model.md#shared-supporting-records). For private defaults, read [Onboarding](../../../docs/development/onboarding.md).
- Decisions explain rationale: [Kratos](../../../docs/adr/ADR-0012-use-kratos-for-human-authentication.md), [application-owned authorization](../../../docs/adr/ADR-0013-keep-authorization-in-access-and-postgresql.md), [bounded delegation](../../../docs/adr/ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [document groups](../../../docs/adr/ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [current account permissions](../../../docs/adr/ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [recovery](../../../docs/adr/ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), and [credential storage](../../../docs/adr/ADR-0048-encrypt-outbound-credentials-in-postgresql-using-pynacl.md). The [decision index](../../../docs/adr/README.md) links the other Access decisions.
- For a detailed policy review, follow the guide’s [maintainer checks](../../../docs/development/access-control.md#maintainer-checks). Read the neighboring jobs, MCP, feedback, or deletion guide only when the task crosses that boundary.

- For application-key questions, follow [current application authority](../../../docs/development/access-control.md#applications), then [credential retry outcomes](../../../docs/development/jobs-and-idempotency.md#secrets). For recovery, use [Access recovery](../../../docs/development/access-control.md#recovery).

- For manager appointment, demotion, removal, and recovery, read [group management](../../../docs/development/access-control.md#group-managers), its [record constraint](../../../docs/development/data-model.md#group-manager-membership-constraint), and [ADR-0049](../../../docs/adr/ADR-0049-require-group-managers-to-be-ordinary-members.md).

## Essential boundaries

A principal is a stable human or application identity. Project membership, document-group reading, group management, and action grants are separate. A caller needs current account/membership/credential validity as well as the required action and document access. Default to denial; do not accept caller-supplied authoritative groups or permissions. Kratos verifies human identity, not product grants.

Bound delegation by the exact action and target. Can-use-and-grant authority is different from can-use authority. Keep human-only administration, peer managers, replacement requirements, separate deletion permissions, and the full issuance checks in the Access guide. Do not infer permission from a title, creator history, installation administration, or membership alone. Every group manager must also have ordinary membership in that same group. Appointment explicitly records both, and reads use membership rather than a manager bypass. Ordinary membership alone never authorizes sharing. Empty document allowlists are never public.

Application keys identify their account and use its current permissions. Issuance requires the authorized human to pass both the management and delegation checks specified in the guide; it is not a permanent ceiling on an issued key. Incoming credential audiences, expiry, overlap limits, revocation, and account deletion remain distinct. Applications cannot acquire human-only grant or incoming-credential administration. Outgoing provider-key management follows its own policy.

Ordinary departure preserves required human management. Demotion removes management but retains membership. Membership removal also removes management, and rejoining does not restore it. Emergency suspension preserves both records while immediately blocking reading and administration, even for the sole manager. Scoped group recovery explicitly assigns both membership and management to an eligible replacement without reviving the compromised account or giving the operator ordinary unrestricted reading. Project, resource, document, group, and application-account deletion each follow their explicit permission and reference rules.

The Access schema uses shared principals with a small project-bound application extension, target-specific current grant tables, one recipient/action/target assignment with `can_grant`, and separate audit history. The migration enforces core scoped relationships, manager membership, principal/resource kinds, grant uniqueness, and application use-only grants. The fixed action catalogue remains application-owned and is not yet enforced by database checks. Every manager record requires the matching group-membership record. Creation, appointment, removal, and recovery must preserve that constraint. All participating writes use the accepted organization/project coordination, current checks, expected scope revisions, mutation, revision increment, and audit commit together. Keep external work outside the short transaction. Audit retention and workflow enforcement still need implementation and tests.

Keep policy in Access and PostgreSQL for v1. OpenFGA and PyCasbin were considered but not selected. Do not add a generic policy language, speculative engine adapter, or authorization cache without a demonstrated need. The [recorded engine comparison](../../../docs/development/access-control.md#section-introduce-a-general-authorization-engine-or-policy-language-now) preserves the actual reconsideration criteria.

All remote model calls use ModelGateway and approved destinations, including embeddings, generation, judges, probes, and repair calls. Check embedding and generation capabilities separately. Credential-only replacement preserves connection meaning but invalidates the relevant probe status. Changed endpoint origin needs a new connection and explicit credential provision; never forward a saved secret to it automatically. PostgreSQL/PyNaCl authenticated encryption with a separate persistent root key is accepted; fail closed and keep plaintext resolution narrow.

## Explain and review

Use Alice and SupportBot: both can belong to Support, while only the bot has Query on Production. Removing Query prevents that action; removing its document-group membership changes readable evidence. Rotating a key changes neither grant. An unrelated Test remains separately protected.

Trace current checks at admission, commit, dispatch, and disclosure as relevant. Cite the precise rule, name proposals and qualification limits, and inspect code before claiming behavior exists. Preserve private defaults and Build plus target-specific Manage releases checks; automatic mode cannot elevate upload-only access. Do not implement future resource domains merely because their grant tables appear in the foundation map.
