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

The current host milestone passed 128 CLI/xtask tests and three doctests with no failures, skips or ignored cases. Context-focused coverage passed nine cases. The meaningful callback and flow failures were observed before implementation, followed by seven real-wire callback cases and seven controlled TLS/flow/handoff/bridge cases passing. These are controlled host results, not a native Ory or operator journey.

Coverage exercises strict input, issuer/path/Host/state association, success/error policy, generated-session binding, one protected handoff, receipt mismatch, uncertain effects, cancellation and independent cleanup outcomes. The ordinary source-built examples have not been executed here as a complete operator procedure. A fixture using synthetic TLS or a child substitute does not prove the installed backend's authority checks, provider behavior or remote exec completion.

Focused controlled checks additionally exercise the shared Rust Deny path with no exchange, generated-session call or maintenance handoff, fixed Deny-before-Allow orchestration, strict denial-result parsing and same-UID bridge framing over a real Unix socket. These checks do not establish an actual combined Rust/provider/browser Deny.

The already delivered account UI has separate eleven-case native private HTTPS/Chromium navigation evidence. That evidence observes actual callbacks with a test-only receiver and deliberately performs no token exchange or proof consumption. It cannot substitute for the combined Rust-driver qualification.

## Dependency advisory applicability

The locked normal graph includes `openidconnect 4.0.1` with `rsa 0.9.10`, and `crypto-bigint 0.5.5` through the P-256/P-384 verification dependencies. The affected versions remain in the graph. Their reviewed use is bounded public verification, not a claim that the packages were patched or are generally safe. Here, public describes the cryptographic verification operands. Tokens, ID-token payloads and callback material remain protected and are not shareable diagnostics.

- [RUSTSEC-2023-0071](https://rustsec.org/advisories/RUSTSEC-2023-0071.html) describes RSA private-key timing leakage and lists no patched version. The inspected OIDC path constructs an RSA public key from public modulus/exponent and verifies a signature. It introduces no private RSA signing or decryption.
- [RUSTSEC-2026-0387](https://rustsec.org/advisories/RUSTSEC-2026-0387.html) describes timing variability involving secret integers, with fixes in `crypto-bigint >= 0.7.6`. The inspected ECDSA verification path consumes a public point, signature and message. It does not introduce secret-key integer operations in this component.

The public OIDC client is constructed without a client secret. Its maintained verifier rejects shared-secret/HMAC signatures in that configuration. Maintained validation checks claims and nonce, and the flow adds subject, authorized-party and access-token-hash binding. Controlled fixture signing uses Ed25519 test keys. PKCE, state and nonce use maintained generation/hash paths rather than custom private-key arithmetic.

This is a call-path applicability assessment for the authored CLI/xtask profile. It does not waive advisories for another caller, a private-key operation, a changed dependency graph or a different algorithm. Reassess the exceptions when those facts change. The pinned `cargo-deny 0.20.2` checks passed for both authored CLI and xtask crates under the existing narrow advisory exceptions. That command result is separate from this source assessment and does not patch the dependencies, waive final source review or establish general safety.

## Qualification still required

The maintained account owner is the intended combined boundary for the actual source-built examples, pinned Ory providers, isolated browser and protected backend handoff. Native/provider/image qualification remains pending. The combined profile requires an actual Rust/provider/browser Deny before Allow under the same original 300-second deadline. The denied driver must exit `1` with exact schema version `1`, `kind: denied` and both cleanup fields `not-needed`. An independent database check must establish no receipt, grant, audit, Access-revision or metadata change before Allow starts. Those cleanup fields do not prove physical cleanup. The second fixed driver must then use the generated session operation and obtain the real repair receipt. Prior Node-only navigation and controlled-layer evidence cannot replace this required native case. Actual artifact execution, no ambient proxy adoption and the positive repair/replay and rejected-input/identity/association cases remain required. Omitting the unsafe ignored host-artifact test does not waive those obligations.

System-browser launch, OS/browser variants, packaged ingress and the complete saved-login lifecycle remain unqualified. The closed fixture does not provide a browser with database, Hydra administration or exec-descriptor authority. Full #160 completion and [human acceptance #298](https://github.com/matejpalenik/inframeld/issues/298) must not be inferred from these controlled results. The ordinary account-selection and unadmitted-bootstrap journeys remain separate.
