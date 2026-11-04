# Transient recipient-proof verification

The implemented component acquires proof for an already-admitted human and hands it to one reviewed Project metadata repair. It shares one Rust OAuth/OIDC owner between the operator example and the private browser adapter. It does not deliver an ordinary CLI login command, saved credentials, refresh/logout, account selection, bootstrap or human acceptance.

Use the [operator guide](../guides/recipient-proof.md) for inputs, invocation, results and recovery. [PD-ACCESS-07](../../../.agents/skills/inframeld-access-models/references/decision-human-cli-issuer-binding.md) owns issuer association. [Host maintenance](../../../.agents/skills/inframeld-access-models/references/host-maintenance.md#project-metadata-authority-repair) owns repair authority and replay.

## Inspected implementation

| Source | Responsibility |
| --- | --- |
| [`auth/mod.rs`](../../../apps/cli/src/auth/mod.rs) and the [operator](../../../apps/cli/examples/recipient_proof.rs) / [native-driver](../../../apps/cli/examples/recipient_proof_native_driver.rs) entry points | Snapshot three bounded proof-free files, dispatch the same operation and report safe result/cleanup facts. |
| [`auth/callback.rs`](../../../apps/cli/src/auth/callback.rs) | Derive the exact issuer path, bind literal loopback and associate success/error before exchange under bounded parsing. |
| [`auth/flow.rs`](../../../apps/cli/src/auth/flow.rs) and [`auth/transport.rs`](../../../apps/cli/src/auth/transport.rs) | Freeze trusted context, use maintained PKCE/OIDC validation, verify generated current-session output and own transient credential cleanup. |
| [`auth/recipient_proof.rs`](../../../apps/cli/src/auth/recipient_proof.rs) | Reject unsupported requests and match the original operation, verified principal, exact responsibility and reviewed revision plus one. |
| [`auth/maintenance_handoff.rs`](../../../apps/cli/src/auth/maintenance_handoff.rs) | Send proof only through protected child stdin and keep commit, process cleanup and credential cleanup independent. |

The operator and qualification examples call this shared owner. Neither obtains proof through administrative approval or accepts a caller-supplied token. A safe receipt is evidence of the original repair, not current grant authority. Unknown output remains uncertain even when the local process was cleaned up.

## Controlled evidence and its limits

The current host milestone passed 146 CLI/xtask tests and three doctests with no failures, skips or ignored cases. Context-focused coverage passed nine cases. The meaningful callback and flow failures were observed before implementation, followed by seven real-wire callback cases and seven controlled TLS/flow/handoff/bridge cases passing. These are controlled host results, not a native Ory or operator journey.

Coverage exercises strict input, issuer/path/Host/state association, success/error policy, generated-session binding, one protected handoff, receipt mismatch, uncertain effects, cancellation and independent cleanup outcomes. [Rejected-input and identity/session cases](../../../apps/cli/tests/recipient_proof.rs) stop before maintenance. [Callback cases](../../../apps/cli/tests/human_oauth_loopback.rs) check association before exchange. The shared transport disables ambient proxy adoption, and the [existing CLI subprocess regression](../../../apps/cli/tests/targets.rs) supplies invalid ambient proxy variables. These are controlled-layer checks, not an additional native rejection matrix. The ordinary source-built operator example has not been executed here as a complete operator procedure. A fixture using synthetic TLS or a child substitute does not prove the installed backend's authority checks, provider behavior or remote exec completion.

Focused controlled checks additionally exercise the shared Rust Deny path with no exchange, generated-session call or maintenance handoff, fixed Deny-before-Allow orchestration, strict denial-result parsing and same-UID bridge framing over a real Unix socket. These checks do not establish an actual combined Rust/provider/browser Deny.

The already delivered account UI has separate eleven-case native private HTTPS/Chromium navigation evidence. That evidence observes actual callbacks with a test-only receiver and deliberately performs no token exchange or proof consumption. It cannot substitute for the combined Rust-driver qualification.

## Dependency advisory applicability

The locked normal graph includes `openidconnect 4.0.1` with `rsa 0.9.10`, and `crypto-bigint 0.5.5` through the P-256/P-384 verification dependencies. The affected versions remain in the graph. Their reviewed use is bounded public verification, not a claim that the packages were patched or are generally safe. Here, public describes the cryptographic verification operands. Tokens, ID-token payloads and callback material remain protected and are not shareable diagnostics.

- [RUSTSEC-2023-0071](https://rustsec.org/advisories/RUSTSEC-2023-0071.html) describes RSA private-key timing leakage and lists no patched version. The inspected OIDC path constructs an RSA public key from public modulus/exponent and verifies a signature. It introduces no private RSA signing or decryption.
- [RUSTSEC-2026-0387](https://rustsec.org/advisories/RUSTSEC-2026-0387.html) describes timing variability involving secret integers, with fixes in `crypto-bigint >= 0.7.6`. The inspected ECDSA verification path consumes a public point, signature and message. It does not introduce secret-key integer operations in this component.

The public OIDC client is constructed without a client secret. Its maintained verifier rejects shared-secret/HMAC signatures in that configuration. Maintained validation checks claims and nonce, and the flow adds subject, authorized-party and access-token-hash binding. Controlled fixture signing uses Ed25519 test keys. PKCE, state and nonce use maintained generation/hash paths rather than custom private-key arithmetic.

This is a call-path applicability assessment for the authored CLI/xtask profile. It does not waive advisories for another caller, a private-key operation, a changed dependency graph or a different algorithm. Reassess the exceptions when those facts change. The pinned `cargo-deny 0.20.2` checks passed for both authored CLI and xtask crates under the existing narrow advisory exceptions. That command result is separate from this source assessment and does not patch the dependencies, waive final source review or establish general safety.

## Qualification still required

The selected Linux ARM64/rootless Podman private-container/Chromium profile passed with the actual source-built native driver and shared production OAuth flow. Under one original 300-second deadline, Deny exited `1` with exact schema version `1`, `kind: denied` and both cleanup fields `not-needed`. The mandatory backend validator independently checked zero receipt, grant and audit effects and unchanged Access revision and metadata before Allow started. Those cleanup fields describe the denied attempt's obligations, not physical cleanup.

The fresh Allow attempt completed generated current-session verification and protected maintenance handoff. The validator required the exact original committed repair receipt, confirmed process and credential cleanup, and the matching database receipts, one grant, one audit, a single Access-revision advance and unchanged Project metadata. The issued access credential's revocation met the existing provider confirmation contract. No refresh credential was issued. Process cleanup, credential cleanup and the separately reconciled physical resource baseline remain distinct observations. This qualifies execution of the source-built native-driver artifact, not the ordinary system-browser operator recipe or a packaged artifact.

Original-receipt replay after grant removal has complementary [PostgreSQL](../../../apps/backend/tests/integration/access/test_project_metadata_host_repair_postgres.py) and [real-provider](../../../apps/backend/tests/integration/access/test_native_project_metadata_host_repair.py) coverage. The maintained full integration run exercised those existing cases with unchanged repair implementation and test inputs, preserving the original result without regrant or another repair audit. That evidence is not a fresh full integration run of this transient acquisition component, and the private browser profile does not itself perform grant removal and replay. Together with the controlled rejection, association and proxy checks above, these layers retain the accepted obligations without restoring the unsafe ignored host-artifact test.

The ordinary operator procedure, system-browser launch, additional OS/browser variants, packaged ingress and the complete saved-login, refresh and logout lifecycle remain unqualified. The closed fixture does not provide a browser with database, Hydra administration or exec-descriptor authority. Full #160 completion, setup and unadmitted bootstrap remain unfinished. [Human acceptance #298](https://github.com/matejpalenik/inframeld/issues/298) remains open and is not ready for handoff. These remaining journeys are not established by the selected native or complementary controlled/provider results.
