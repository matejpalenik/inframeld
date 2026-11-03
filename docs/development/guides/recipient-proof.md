# Acquire transient proof for a reviewed metadata repair

Alice already belongs to Support, but no eligible human can grant its Project metadata action. A trusted host operator has reviewed that stranded responsibility. The maintained Rust example can sign Alice in, verify her current Inframeld session and send fresh proof directly to the existing backend repair command. Host execution authorizes the repair. The proof identifies its recipient.

The shared capability and example entry points are implemented. Controlled checks are separate from native provider, system-browser and combined repair qualification, which remain pending. This is not a completed human operator procedure. [Human acceptance #298](https://github.com/matejpalenik/inframeld/issues/298) remains open. No ordinary CLI login command, saved login, refresh, logout or bootstrap is supplied by these examples.

## Establish the prerequisites

- Use the repository's pinned Rust toolchain and locked dependencies. The examples are source-built and are not commands in a published CLI release.
- Independently verify the managed installation, exact public HTTPS API and issuer, official `inframeld-cli` registration and intended Kratos identity. Preserve the issuer's spelling and trailing slash. Discovery is a comparison against these trusted facts, not authority to choose them.
- Keep Hydra administration private and trusted. The honest server must not register another issuer's callback or permit attacker-controlled registration or alternative approval. Provisioning alone cannot certify these deployment conditions.
- Alice must already be an active admitted human and a member of the Project. Review the exact Project UUID and its current **Access revision**, which is different from `metadataRevision`.
- Run compatible backend code at schema `0015_artifact_allocation`, with its original installation identity and database/provider/fingerprint-key configuration. Schema `0014_project_metadata` introduced the repair consumer. Follow the [consumer runbook](../operations/project-metadata-repair.md) for server setup and authority checks.
- Have independently trusted host/container-exec authority for that backend. Browser consent or a target label cannot supply it.

## Prepare three proof-free files

Use an operator-owned directory with mode `0700` and regular files with mode `0600`. Do not include a token, cookie, PKCE verifier or provider password. The helper snapshots all three files before browser/provider/maintenance effects. It rejects symlinks, non-regular files and files larger than 65,536 bytes. Protect the directory yourself rather than treating parsing as proof of host authority.

The following are complete JSON templates. Replace every example identity and host path with independently reviewed values. No example UUID is an installation default.

Save `/absolute/operator/recipient-repair/host-context.json`:

```json
{
  "schemaVersion": 1,
  "api": "https://api.example.com",
  "issuer": "https://identity.example.com/",
  "clientId": "inframeld-cli",
  "installationId": "00000000-0000-4000-8000-000000000001",
  "expectedIdentityId": "00000000-0000-4000-8000-000000000002",
  "certificateAuthorities": []
}
```

This template uses normal platform trust. For a private CA, supply its actual public PEM text in `certificateAuthorities`, with at most 16 array entries. An optional `proxy` is explicit transport configuration. Ambient proxy variables are not adopted. API and issuer strings are each limited to 8,192 bytes. The expected identity is a Kratos identity UUID, not the local principal ID later returned by the session API.

Save `/absolute/operator/recipient-repair/request.json`:

```json
{
  "schemaVersion": 1,
  "mode": "repair-stranded-authority",
  "expectedInstallationId": "00000000-0000-4000-8000-000000000001",
  "operationId": "support-metadata-repair-01",
  "operatorLabel": "support-operator",
  "reason": "Restore the reviewed stranded metadata responsibility",
  "expectedAccessRevision": 7,
  "expectedIdentityId": "00000000-0000-4000-8000-000000000002",
  "responsibility": {
    "kind": "action-grantor",
    "target": {
      "kind": "project",
      "projectId": "00000000-0000-4000-8000-000000000003"
    },
    "actionId": "edit-project-metadata"
  }
}
```

Keep this original `operationId` and request meaning after lost output. The reviewed revision is a nonnegative integer. `operationId` and `operatorLabel` are nonblank and at most 128 Unicode code points each, and `reason` is nonblank and at most 512. The nine fields above are the complete proof-free request. Adding `identityProof`, selecting bootstrap or supplying another action is rejected before browser or maintenance effects.

Save `/absolute/operator/recipient-repair/exec-spec.json`. This template uses the existing [non-PTY Compose transport](../getting-started/local-setup.md#resume-recovery-cleanup). Replace the program, Compose file and explicit environment with the verified host's values:

```json
{
  "program": "/absolute/path/to/podman",
  "args": [
    "compose",
    "-f",
    "/absolute/path/to/inframeld/compose.dev.yaml",
    "exec",
    "-T",
    "backend",
    "inframeld-maintenance"
  ],
  "environment": {
    "HOME": "/absolute/operator/home",
    "PATH": "/absolute/operator/bin:/usr/bin:/bin",
    "XDG_RUNTIME_DIR": "/absolute/operator/runtime"
  }
}
```

The installed backend command is `inframeld-maintenance`. Its module equivalent is `python -m inframeld_backend.maintenance`. The backend container owns its database, private provider and fingerprint-key configuration. The descriptor chooses direct argv execution without a shell or PTY, and the child receives only the explicit environment. Review any Compose provider executable needed by your host. Do not move proof into argv or environment variables.

`program` must be absolute and at most 8,192 encoded bytes. `args` allows at most 256 strings of at most 8,192 bytes each. `environment` defaults to an empty map with at most 64 unique, nonempty names. Names cannot contain `=` or NUL. No argument or environment value may contain NUL. All three JSON files reject unknown or duplicate fields and a second JSON value.

## Start one reviewed attempt

From the repository root, the source-built operator example accepts these exact arguments. This recipe has been checked against source, not executed as a complete operator journey:

```bash
mise exec -- cargo run --locked -p inframeld-cli --example recipient_proof -- \
  --host-context /absolute/operator/recipient-repair/host-context.json \
  --request /absolute/operator/recipient-repair/request.json \
  --exec-spec /absolute/operator/recipient-repair/exec-spec.json
```

The helper derives the callback path from the full SHA-256 of the exact issuer UTF-8 bytes and binds literal `127.0.0.1` at an ephemeral port. It opens the browser only after freezing the attempt. Sign in as the reviewed existing human and check the account and installation before approving. Cancellation is an explicit choice. Keep flow URLs and authorization codes out of logs and screenshots.

The shared owner associates success and error callbacks with that listener, Host/path, state and issuer policy before exchange. Discovery must already match the frozen installation/API/issuer/client binding. Maintained ID-token validation checks the intended Kratos identity. The generated `get_current_session` call then verifies an admitted human and supplies the local principal ID. The transient access token goes directly into protected backend stdin and is never printed or saved as a login.

One interaction has a ten-minute deadline. Individual network requests are bounded to five seconds. Maintenance has at most 30 seconds, including a five-second stdin budget, clipped to the original deadline. Process cleanup has separate five-second TERM and five-second KILL/reap bounds. Transient credential revocation has an independent five-second budget. These limits do not prove a remote exec operation rolled back.

The callback has raw request-target and parser caps of 128 KiB and 192 KiB, plus 32 KiB/32 header limits. The maintained HTTP URI type also rejects wire targets above 65,534 bytes. The raw caps do not promise acceptance of every target up to 128 KiB.

## Read the result before deciding what to do next

After argument parsing, the helper writes one secret-safe JSON result. Help uses plain text, and malformed arguments produce a safe usage failure. Interrupted or failed output can leave incomplete JSON. A `result` separates `maintenance.effect`, `maintenance.processCleanup`, any maintenance `failure` and `credentialCleanup`. A top-level `error` identifies a failed stage and independent cleanup facts. Ordinary errors do not include provider bodies, token text or child output.

| Observation | Meaning and recovery |
| --- | --- |
| Exit `0` | A matching committed receipt, process cleanup and transient credential cleanup were confirmed, with no maintenance failure. |
| Committed receipt with nonzero exit | Preserve the confirmed repair even if later reporting or cleanup failed. Resolve the separate cleanup problem without creating a new repair. |
| Unknown maintenance effect | The backend may have committed. Keep the original `operationId` and reviewed meaning. There is no automatic resubmission or rollback claim. |
| Exit `2` | Invalid arguments, protected input or trusted setup. Correct the input. Do not weaken recipient or installation checks. |
| Exit `1` | Failure, unknown outcome, incomplete cleanup or result-output failure. Inspect the safe result before any further action. |
| Exit `130` or `143` | Interrupted by SIGINT or SIGTERM. Any confirmed receipt remains meaningful. Missing output does not prove no effect. |

A checked authorization denial reports `error.kind: denied` and exits `1`, without exchange, session verification or maintenance handoff. Its `resourceCleanup: not-needed` and `credentialCleanup: not-needed` describe that attempt's obligations. They are not evidence that a browser or container was physically cleaned up.

A receipt must match the original mode, operation, installation, verified principal, exact responsibility and reviewed Access revision plus one. In the illustrative request above, a valid receipt has `accessRevision: 8`. A child exit alone is not a receipt.

After uncertainty, independently reconcile the original operation. Any explicit retry must keep the original request meaning and operation ID and acquire current proof for the same human. The backend can return the original receipt before fresh-write revision checks. Replay after grant removal returns that receipt without restoring the grant. Never choose a new operation ID merely to make a lost response disappear.

Credential cleanup is separate from commit. Confirmed revocation does not undo repair, and unconfirmed revocation is not proof that credentials are gone. The helper revokes only its newly issued credential set, never an earlier saved login. Preserve cleanup uncertainty for the operator. Browser history and the independently launched browser can outlive the helper.

## Maintained qualification adapter

The source-built `recipient_proof_native_driver` example uses the same three flags plus `--browser-bridge ABSOLUTE_SOCKET`. It replaces browser dispatch with one protected authorization-ready event, not another OAuth implementation. The bridge requires an absent socket under a fresh mode-`0700` parent, a same-UID peer and mode-`0600` socket, with a 128 KiB message bound. The browser still cannot choose callbacks, claims or provider endpoints.

The existing account fixture owns combined container qualification through `scripts/test-account-ui.sh --recipient-proof`, or `INFRAMELD_CONTAINER_RUNTIME=podman scripts/test-account-ui.sh --recipient-proof` for the selected Podman engine. Only the coordinator launches it under the exclusive fixture grant. It source-builds both examples and gives host/request/exec input only to two fixed driver services. One original 300-second phase requires Deny first, independent verification of no repair effects, then Allow through generated session verification and real repair. It includes both readiness gates and all three service outcomes. Each attempt has fresh protected bridge state, PKCE, state and nonce. Native execution remains pending. This is not an automatic retry or an extra production mode. Its source preparation, image build, startup and cleanup keep the existing 30-, 600-, 180- and 60+5+5-second bounds. See the [fixture guide](../../../apps/web/tests/fixtures/README.md#evidence-boundaries-and-remaining-combined-qualification) and [verification report](../reports/recipient-proof-verification.md) for implemented checks and pending native coverage. Private fixture identity seeding or administration is not an operator proof-acquisition shortcut.
