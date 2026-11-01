# Project metadata authority repair

The backend implements a narrow host-authorized repair for an existing Project whose `edit-project-metadata` grantor responsibility is stranded. This runbook describes that consumer and its failure/replay behavior.

**The proof-acquisition prerequisite is currently unmet in the shipped product.** There is no documented, qualified entry point for an operator to acquire the required fresh human Hydra proof. The stock CLI exposes no login command, and the complete client/account-UI acquisition journey remains unqualified. OAuth client provisioning does not sign in a human. This is not a complete usable first-grant walkthrough. The consumer applies only when a separately qualified producer supplies current proof. Proposed client/UI work and private provider tests do not satisfy that prerequisite.

Complete human sign-in, fresh proof, protected repair and rename acceptance is deferred to [human operator qualification (#298)](https://github.com/matejpalenik/inframeld/issues/298). The acquisition prerequisites remain [#82](https://github.com/matejpalenik/inframeld/issues/82) and [#160](https://github.com/matejpalenik/inframeld/issues/160). This deferral does not make the operator walkthrough usable. Server proof verification, current authorization, protected stdin, replay safety and backend, SDK and CI qualification remain required.

## Establish the authority and reviewed state

Host/container-exec authority authorizes repair. The recipient's token identifies the human receiving the exact responsibility. It does not supply operator authority. Use the verified managed backend and an independently controlled installation record, not an API-reported identity, target label, email or Docker context as host proof.

The recipient must already be an active admitted human and current member of the active Project. The exact action must have no active eligible human grantor. Unavailable facts cannot establish that it is stranded. Repair creates neither a principal nor membership, a Project or a starter. The eighteen-action creator contract remains selected provisioning behavior for its owning creation/starter work, not automatic assignment by this repair.

Review the exact Project UUID, recipient's Kratos identity UUID and current Project **Access revision** through protected operator records. The public metadata response's `metadataRevision` is a different revision and cannot substitute for this review.

Apply schema `0014_project_metadata` explicitly through the [upgrade and migration procedure](upgrades.md#upgrades). Startup does not migrate or replace missing installation identity. Use compatible backend code and the original installation identity.

## Configure the existing consumer

The installed backend exposes `inframeld-maintenance` and `python -m inframeld_backend.maintenance`. Both take no command arguments and read one protected stdin JSON object, at most 64 KiB (65,536 bytes). There is no public maintenance HTTP endpoint or Rust CLI repair command.

This repair mode needs the configured application database, private Hydra administration, current Kratos identity verification including its private API, and the existing request-fingerprint key. Its settings are `INFRAMELD_DATABASE__*`, `INFRAMELD_HYDRA__*`, `INFRAMELD_KRATOS__*` and `INFRAMELD_REQUEST_FINGERPRINT__KEY_FILE`, with optional logging/authentication timeouts. Keep administration private. The command reads process environment configuration, not the API's dotenv files automatically. The separate `resume-recovery-cleanup` mode retains its narrower configuration contract.

A fresh Hydra access token must match the configured issuer, official `inframeld-cli` client, exact API audience, required scope, installation/generation binding and current eligible human identity. An arbitrary Hydra token, ID token, refresh token, browser cookie or application key cannot replace it. No token-minting or administrative approval shortcut is part of this procedure.

## Preserve the exact request meaning

The runtime accepts only this subset of host repair:

| Field | Meaning |
| --- | --- |
| `schemaVersion`, `mode` | Integer token `1` and literal `repair-stranded-authority` |
| `expectedInstallationId` | Independently controlled original installation UUID |
| `operationId` | Original operator request ID, retained across response loss |
| `operatorLabel`, `reason` | Bounded operator attribution and repair reason |
| `expectedAccessRevision` | Exact reviewed Project permission revision |
| `expectedIdentityId` | Recipient's current Kratos identity UUID |
| `identityProof` | Typed `hydra-access-token` proof, supplied transiently through protected stdin |
| `responsibility` | `action-grantor`, target `project` with one `projectId`, and literal `edit-project-metadata` |

Unknown fields, duplicate JSON keys, another JSON value, non-integer version/revision tokens and unsupported responsibilities fail validation. General bootstrap, group repair and other action grants are unavailable through this consumer. Keep proof out of arguments, environment variables, normal output, audit and replay records. This runbook supplies no token-bearing shell history or temporary-file recipe.

The runtime-owned [mapper](../../../apps/backend/src/inframeld_backend/access/cli/mappers/project_metadata_maintenance_mapper.py) owns the exact request fields. A design schema cannot establish proof validity, current eligibility or stranded authority. Do not invoke the consumer using an invented acquisition flow.

## Interpret the result and recover

Provider verification finishes before the repair's protected write transaction. Under current coordination, the service rechecks installation, identity, eligibility, membership, Project state, reviewed Access revision and absence of an eligible grantor. It atomically records the exact use-and-grant assignment, advanced Access revision, operator attribution, audit and original receipt.

Exit `0` returns one stdout JSON object with `schemaVersion`, `mode`, `operationId`, `installationId`, `principalId`, `accessRevision`, `outcome: repaired` and the exact safe `responsibility`. This is an original-operation receipt, not proof of today's permissions. Diagnostics go to stderr and must not echo the proof.

| Failure | Meaning and next step |
| --- | --- |
| Exit `2`, `invalid_input` | Correct malformed/unsupported input or configuration. There is no `--mode` argument. |
| `invalid_identity_proof` | Obtain valid proof for the same intended human through a qualified producer. Do not change the recipient assertion to match an unrelated token. |
| `identity_ineligible` | Current human eligibility or Project membership does not permit repair. Host execution does not bypass that requirement. |
| `installation_mismatch` | Stop and reconcile the independent installation/backend binding. Never initialize a replacement identity. |
| `stale_revision` | The new-write review is outdated. Reassess current stranded authority before a distinct new repair. |
| `responsibility_not_stranded` | An eligible human grantor exists or the exact repair is ineligible. Use the owning ordinary administration path when delivered, not broader host assignments. |
| `idempotency_key_reused` | The request ID belongs to different mode, identity or meaning. Do not overwrite that history. |
| `dependency_unavailable` or `unexpected_error` | The result could not be established. Preserve the original request context and investigate safe diagnostics. |
| Missing/interrupted stdout | The transaction may have committed. Do not assume repair failed or issue a new request ID. |

Controlled failed operations use exit `1` and a safe JSON code, with the original request ID when available. After uncertain output, repeat the same operator request ID and original meaning with currently valid proof for the same identity. Replaceable token bytes are excluded from the stable fingerprint. All maintenance modes share the installation/request-ID namespace.

Every invocation verifies current proof and recipient eligibility. A matching completed receipt is returned before fresh-write stranded/revision checks. Replay after grant removal returns that original receipt without restoring the grant. Changed mode, target, reviewed revision, attribution, reason or recipient conflicts. Neither replay nor possession of the receipt grants new authority.

Read the [metadata authority decision](../../../.agents/skills/inframeld-access-models/references/decision-project-metadata-authority.md) and [host-maintenance contract](../../../.agents/skills/inframeld-access-models/references/host-maintenance.md#project-metadata-authority-repair) for the accepted boundary. [Local setup](../getting-started/local-setup.md#configure-the-cli-client) distinguishes official client provisioning from the still-missing interactive acquisition journey.
