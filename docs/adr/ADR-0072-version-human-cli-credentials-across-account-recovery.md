# ADR-0072: Version human CLI credentials across account recovery

**Status:** Accepted. [ADR-0073](ADR-0073-carry-explicit-authentication-evidence-in-access-contexts.md) refines the request context to require explicit authentication evidence. The versioning decision remains unchanged.

**Date:** 2026-10-24

## Context and Problem Statement

Alice starts CLI login with credential version 6. Its approval is delayed. Recovery removes her existing grants, but the approval can reach Hydra afterward and create an active grant. A temporary Inframeld recovery block protects her account only while that block remains.

[ADR-0070](ADR-0070-use-bulk-hydra-revocation-for-identity-recovery.md) selects bulk cleanup. [ADR-0071](ADR-0071-use-native-kratos-login-and-checked-hydra-consent.md) establishes native Kratos login and checked consent. This decision supplements both with permanent rejection of stale CLI credentials at Inframeld. It refines principal-only request-context guidance to permit non-secret credential binding evidence, without freezing account status or permissions.

## Considered Options

- Repeat checks and bulk deletion. Another request may still finish after the final deletion.
- Drain every consent, code exchange and refresh before completion. This requires coordinating remote requests whose outcomes can remain uncertain.
- Keep bulk cleanup and persist one credential version per identity. This is selected. Inframeld rejects an old generation independently of when Hydra finishes issuing it.

## Decision Outcome

Access owns a positive BIGINT credential version keyed by installation, provider authority and subject. It does not require a local principal. Version state is initialized at 1 and is never reset, pruned or downgraded.

A new trusted recovery admission increments the version in the same transaction as its original operation and block. Duplicate delivery does not increment it. Independent overlapping recoveries each invalidate the preceding generation. Release never decreases the version or releases another flow's block.

An allow decision initializes and captures state after reading and validating Hydra's trusted request and before checking the browser session. It approves only if the initial and final observations are unblocked, retain the same version and installation, and match the verified subject. An initially blocked attempt remains rejected even if its block clears during verification. Inspection and denial do not initialize versions.

The consent adapter supplies `inframeld_installation_id` and `inframeld_credential_version` in Hydra's access-token session metadata. Refresh retains the original values. The server never upgrades an old grant by stamping today's version onto it. Clients cannot choose these values.

Human bearer authentication privately introspects the token, checks current Kratos eligibility and compares its binding with current PostgreSQL state. `AccessContextDTO` carries the actor and, under ADR-0073, required non-secret authentication evidence. OAuth evidence retains the captured binding. Both current authorization families recheck that binding through their existing facts projections before lookup, replay or mutation. SQL reports the installation/actor relationship and current version. The shared application evaluator interprets evidence, and the domain policy decides currentness. Their existing transaction and lock ownership remains unchanged.

Stale or missing token binding metadata yields the generic 401 and Bearer `invalid_token` challenge. Otherwise current credentials retain normal 403 eligibility/permission outcomes. Required unavailable state yields 503. No version or recovery details are returned to callers.

## Consequences

Alice's late version-6 grant can remain active in Hydra, but cannot regain Inframeld access after her current version becomes 7 and the block is released. A fresh verified login can use version 7. Bob's version and application keys are unaffected. Opaque tokens remain selected.

This is an Inframeld API guarantee, not a promise that Hydra rejects refresh or `/userinfo` for every stale grant. Those provider capabilities are observed separately. Future gateway routing must keep administration private and expose only required protocol endpoints, blocking external `/userinfo` if supported clients do not need it.

Deploy the schema and backend together. Existing human CLI tokens lack metadata and require a fresh sign-in. There is no unversioned compatibility path or mixed-version deployment support. Preserve installation/version state during maintenance and backup. Rolling back its security state is not a supported way to restore service.

The future CLI checks `/v1/session` before saving credentials, uses bounded refresh handling and removes confirmed invalid credentials only for the selected target/account. It protects concurrent replacement and asks for explicit sign-in. Local deletion does not revoke other copies. Permission denial or provider unavailability does not clear a login.

Production completion remains unwired. Verified password replacement, native session cleanup, durable execution, trusted outcomes and remaining provider-internal race qualification are separate requirements. Controlled test completion does not establish production callback safety.

## Implementation notes

The consent service has separate read-only and approval paths. Unsupported access is rejected before initialization or browser verification. Supported approval still captures state before verification, even if the browser later fails. Its preparation method returns a required binding containing the original version, rather than an optional result controlled by a flag. This clarifies the implementation without changing version advancement, transaction ownership or the stale-credential guarantee.

## Links

- [Current credential-version behavior](../development/access-control.md#human-credential-versions)
- [Version records and binding evidence](../development/data-model.md#human-credential-version-records)
- [Consent implementation](../../apps/backend/src/inframeld_backend/access/application/services/human_oauth_consent_service.py)
- [PostgreSQL version scenarios](../../apps/backend/tests/integration/access/test_human_credential_versions_postgres.py)
- [Native consent and ordering scenarios](../../apps/backend/tests/integration/access/test_native_hydra_consent.py)
- [Hydra v26.2 session metadata contract](https://github.com/ory/hydra/blob/v26.2.0/flow/consent_types.go#L651)
- [OWASP authorization guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)
