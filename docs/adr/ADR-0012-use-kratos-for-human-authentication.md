# ADR-0012: Use Kratos for human authentication

Status: Accepted

**Date:** 2026-09-17

## Context and Problem Statement

Human sign-in, sessions, recovery, and optional company identity-provider login need a consistent identity system. These concerns are separate from project and document permissions inside Inframeld.

## Considered Options

- Use Kratos for human identity and sessions, with deployment-level external OIDC sign-in.
- Use Keycloak or ZITADEL; the original record lists them as not selected without a full comparative assessment.
- Introduce Hydra or Inframeld-owned OAuth issuance for the v1 browser flow.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Use Kratos for human authentication. Resolve a verified identity source and subject to a stable local human principal. Support deployment-configured external OIDC sign-in through Kratos in OSS. Inframeld continues to own application authorization; upstream email addresses and group claims do not automatically merge local accounts or grant access.

**Example.** Alice can sign in successfully and still have no rights in Finance. Her sign-in proves identity; the current application policy decides whether a Finance operation is allowed.

## Consequences

- The application can share a human identity boundary across local and deployment-level external sign-in.
- Inframeld still needs account screens, session integration, CSRF protection, controlled bootstrap, recovery integration, and deployment tests. This choice supplies neither a global application administrator nor delegated-user access.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current access control](../development/access-control.md).
- [Current onboarding](../development/onboarding.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0013](ADR-0013-keep-authorization-in-access-and-postgresql.md), [ADR-0014](ADR-0014-bound-permission-delegation-by-action-and-exact-target.md), [ADR-0015](ADR-0015-keep-document-group-access-separate-from-operational-permissions.md), [ADR-0016](ADR-0016-use-stable-shared-principals-with-an-application-account-extension.md), [ADR-0017](ADR-0017-let-valid-application-keys-use-current-account-permissions.md), [ADR-0018](ADR-0018-use-opaque-expiring-and-revocable-application-credentials.md), [ADR-0019](ADR-0019-permit-emergency-suspension-with-scoped-operator-recovery.md), [ADR-0020](ADR-0020-store-current-grants-in-target-specific-relational-tables.md), [ADR-0021](ADR-0021-separate-current-grants-from-transactional-audit-history.md), [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md).
- Delivery boundary: the shared Access foundation establishes common identity, grants, and scoped persistence rules. Human sessions, private defaults, administration and handover, document-access checks, and incoming credentials remain with their owning workflows.
