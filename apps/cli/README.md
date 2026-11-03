# Inframeld CLI foundation

The Rust `inframeld` executable provides offline help/version and credential-free `target add`, `target use` and `target show`. Help and version require no services, configuration or credentials. Registration validates public HTTPS discovery, while selection and readback use local state. Login, account/Project selection and other product commands remain separate delivery work. Full #158 and #159 remain open. The [common automation contract](../../.agents/skills/inframeld-application-contracts/references/cli-output-and-automation.md) is accepted design. Its offline version consumer is described below, while progress, queries, lists and mutations still need their owning executable integrations.

```sh
inframeld --help
inframeld version
inframeld version --help
```

No arguments displays help. Invalid arguments exit with code 2. Help and version require no network, configuration, credentials, Docker or writable home. The generated SDK adapter is exercised through an isolated HTTP test, not exposed as an extra product command.

## Inspect offline version output

Use `inframeld version --json` to inspect the installed executable in a script. The [user guide](../docs/src/app/guides/inspect-cli-version/page.mdx) explains its fields and recovery limits. This command reads embedded build information, not a running installation. Development metadata reports no qualified runtime and leaves remote compatibility unverified.

`--json` writes one final JSON object to stdout. Explicit `--jsonl` writes one compact final record whose `result` contains that object. Neither version nor its dry-run emits progress. Choose one output mode. Both flags together produce a JSON usage failure and exit 2. Help and a recognized root `--version` remain plain-text exceptions.

`inframeld version --dry-run --json` describes the intended embedded-metadata read and stdout output without reading the embedded values. It checks arguments only. Its successful plan does not verify build metadata, runtime readiness or compatibility. `--no-input`, `--plain` and `--no-color` are accepted global booleans, but version never prompts and these flags do not change JSON data. These global flags can appear before or after `version`. The target selector is irrelevant to offline version output.

### Manually check the version feature

Use a binary built with this feature, either installed as described below or built from source. Older archives may reject the new flags. From any working directory with that binary on `PATH`, run these commands individually:

```sh
inframeld version
inframeld version --json
inframeld --json version
inframeld version --jsonl
inframeld version --dry-run
inframeld version --dry-run --json
inframeld version --dry-run --jsonl
```

Each exits 0 when output is written successfully. Human version output retains the embedded version, revision, dirty-source flag, target and compatibility policy, ending with `Remote compatibility: unverified`. Both ordinary JSON flag positions produce the same fields. Their six required top-level fields are `schemaVersion`, `mode`, `outcome`, `data`, `error` and `warnings`. Execute mode has the nine version-data fields documented in the user guide. Unknown embedded revision becomes JSON `null`, independently of `sourceDirty`. `qualifiedRuntime` is `null` for this development profile. JSONL contains exactly one final `type: "result"` record, with no progress or trailing record. Successful stderr is empty.

Human dry-run says that embedded values were not read and remote compatibility was not checked. Machine dry-run has `mode: "dryRun"`, `outcome: "succeeded"`, `operationPerformed: false` in its plan data, `error: null` and `warnings: []`. It contains intended actions rather than actual metadata values.

Check a rejection and the plain-text exceptions separately:

```sh
inframeld --json
inframeld version --json --jsonl
inframeld version --help --json
inframeld --json --version
```

The first two exit 2, with `outcome: "failed"`, `data: null` and the safe `invalid_arguments` error on stdout, plus a fixed diagnostic on stderr. No submitted argument values are echoed. The last two display plain text and exit 0. An exact help flag before standalone `--` takes precedence over argument errors or conflicting output modes. Tokens after that delimiter do not select machine output or dry-run.

These checks change no configuration, credentials or installation data and need no cleanup. Redirecting output creates files only through the shell. Treat a missing, malformed or incomplete machine result as failed output and check the process status. A machine stdout write or flush failure, including a broken pipe, exits 1 and may leave only a prefix. It never appends a replacement result. Plain human/help/version output preserves its existing broken-pipe exit 0 behavior. Forced termination can prevent any final output. The feature adds no signal or durable-work workflow.

## Install and remove a packaged executable

Choose the archive matching your OS and architecture. The planned matrix is Apple Silicon and Intel macOS (native CI targets macOS 15), and ARM64 and x86-64 Linux with glibc 2.35 or newer (Ubuntu 22.04 baseline). These are qualification targets. The macOS 13 deployment setting is a build constraint, not a qualified minimum supported OS. Only the platforms actually executed in the report have verification evidence. See the [verification report](../../docs/development/reports/cli-foundation-verification.md) for actually executed platforms. Windows, musl Linux and signed/notarized macOS distribution are not qualified here.

Download the archive and its `.sha256` file from the same explicit artifact set. Verify **before extracting or installing**:

```sh
# macOS
shasum -a 256 -c inframeld-cli-aarch64-apple-darwin.tar.xz.sha256
# Linux uses: sha256sum -c <archive>.sha256
# Replace this example archive with your chosen platform.
tar -xf inframeld-cli-aarch64-apple-darwin.tar.xz
```

In the extracted directory, use this explicit user-local installation recipe. It refuses to overwrite an existing executable. Choose another directory or deliberately remove the old executable first. No shell startup file is edited.

```sh
bin_dir="$HOME/.local/bin"
mkdir -p "$bin_dir"
(test ! -e "$bin_dir/inframeld" && install -m 755 inframeld "$bin_dir/inframeld")
"$bin_dir/inframeld" --help
# If needed, add this directory to PATH yourself for this shell:
export PATH="$HOME/.local/bin:$PATH"
```

A failed permission check requires a writable bin directory, not sudo or deleting application data. Paths containing spaces are supported when quoted. To remove the executable, remove only the file you installed:

```sh
rm "$HOME/.local/bin/inframeld"
```

Installing/removing a binary neither starts, stops, upgrades nor resets an installation. It does not change targets, logins or data. Checksums detect accidental/corrupt content relative to the checksum file. They do not authenticate an untrusted download source. Public release hosting/signing belongs to separate release work.

## Build and check from source

Use Rust 1.95.0 with rustfmt and Clippy. If `cargo` is missing, install Rust using [rustup](https://rustup.rs/), then run `rustup toolchain install 1.95.0 --component rustfmt --component clippy`. Run from the repository root:

```sh
cargo build --locked -p inframeld-cli -p inframeld-cli-xtask
cargo run --locked -p inframeld-cli --bin inframeld -- --help
cargo fmt -p inframeld-cli -p inframeld-cli-xtask --check
cargo clippy --locked -p inframeld-cli -p inframeld-cli-xtask --all-targets --all-features --no-deps -- -D warnings
cargo test --locked -p inframeld-cli -p inframeld-cli-xtask --all-features
RUSTDOCFLAGS='-D warnings' cargo doc --locked -p inframeld-cli -p inframeld-cli-xtask --all-features --no-deps
cargo install --locked --version 0.20.2 cargo-deny
cargo deny --manifest-path apps/cli/Cargo.toml --locked check
```

The private pnpm wrapper integrates `@inframeld/cli` with repository lint, typecheck, test and build. CLI Turbo tasks disable caching so shared Cargo/SDK changes cannot reuse stale results. Formatting checks also include Rust. Both authored crates deny missing public documentation. Strict documentation checks include every feature, while generated SDK settings remain separate. To inspect internal component documentation, add `--document-private-items` to the `cargo doc` command above. End users of archives need none of Rust, Node, pnpm or Python.

The [discovery dependency assessment](../../docs/development/reports/server-discovery-verification.md#dependency-audit-assessment) documents the two approved advisory exceptions in `deny.toml` and when their applicability must be reassessed.

## Package without publishing

CI downloads the pinned cargo-dist archive and checksum with a 10-second connection limit and a 60-second limit per transfer attempt. Transient download failures allow three retries within a 120-second retry window. An in-progress attempt retains its own transfer limit. The downloaded archive still requires checksum verification before extraction. Test assertions and checksum failures are not retried.

Packaging helpers are the private Rust `xtask` crate and require no Python. Install the pinned tool with `cargo install --locked --version 0.33.0 cargo-dist`. A missing `dist` command means that tool must be installed and its bin directory put on PATH. From the repository root:

```sh
cargo xtask package --target aarch64-apple-darwin --reproducible
# Omit --target to build for this machine.
# Omit --reproducible for one build during local iteration.
# This builds, normalizes, checksums and tests without publishing.
```

Cargo-dist 0.33.0 is build-only, with no installers, publishers, updater or automatic release creation. After cargo-dist builds, the Rust normalization helper preserves payloads and executable bits while setting sorted paths, root ownership and SOURCE_DATE_EPOCH timestamps, then regenerates SHA-256 checksums. Archives contain the executable, Apache license, this guide and compatibility metadata. The same task runs locally and in CI, with explicit Result-based qualification failures in debug and release builds. Its manifest records artifacts and checksums. The native CI jobs also record compiler, source revision, target and the binary's embedded build information in verification evidence. Ordinary compilation never generates SDK sources or starts a backend.

Use a clean checkout and locked inputs for qualification. Linux packaging runs on native Ubuntu 22.04 builders. The CI rebuild compares archive and binary hashes in the same environment. A mismatch fails qualification rather than being described as reproducible. Cross-host bit reproducibility and package signing are not established by a repeated local build.

## Compatibility and ownership

[ADR-0095](../../docs/adr/ADR-0095-support-matching-qualified-cli-and-runtime-releases.md) selects matching explicitly qualified releases. The checked-in compatibility descriptor owns policy fields. Cargo supplies the package version and the build script generates one metadata document with revision, dirty-source status and target. CLI output, archived metadata and qualification evidence consume that document. A development archive does not imply a clean or released revision. Current version `0.0.0` is a development build, with no qualified released runtime. `inframeld version` reports source revision, target and **Remote compatibility: unverified**. Health and login cannot prove release compatibility. Automatic remote checks await the owning backend contract.

The command/parser and output layers handle local presentation only. Explicit connection inputs do not discover targets, enforce remote trust policy, read environment selections or establish permissions. Product application calls use `inframeld-sdk`, preserving typed errors, response metadata, bounded timeouts and disabled automatic retries/redirects. A decode or acknowledgment failure never authorizes another dispatch. Credential storage and saved selections remain with #159/#160. The stateless discovery library is described below.

## Rust tooling layout

The runtime starts in `src/main.rs`, with parsing, dispatch and bounded final reporting in private `src/app.rs`. The library preserves `inframeld_cli::run` through a re-export. `src/commands/version.rs` maps validated embedded metadata into typed version data and supplies its descriptive plan. Human version still uses `BuildMetadata::render`, which also supplies the text checked by packaging qualification. This offline consumer does not establish a general product-command framework.

The private xtask follows the same entry-point split: `src/main.rs` reports the result, `src/arguments.rs` declares clap inputs and `src/app.rs` dispatches them. `src/package.rs` coordinates packaging through `PackagingContext`, which owns resolved build inputs and configured commands. `src/verify/mod.rs` retains the verification API and evidence record, `src/verify/inspect.rs` checks archives before execution and `src/verify/native.rs` owns native installation and execution qualification. Archive and bounded-process mechanics remain in `src/archive.rs` and `src/process.rs`.

`cargo xtask package` owns the complete build, metadata stamping, normalization, checksum, installation/removal and native execution path. `--reproducible` forces a second CLI compilation and compares typed evidence. `cargo xtask verify <archive> --target <target>` checks an already normalized native archive. `cargo xtask normalize <archive> --epoch <seconds>` is the low-level normalization command. Commands are build-only and do not publish.

Archive reads reject unsafe paths, links, duplicates, unexpected files and oversized payloads. Compatibility metadata is validated before executing the bundled binary. The verifier compares its output with the exact archived metadata, exercises permission failures as an unprivileged user, and uses bounded child-process waits. Qualification failures return errors even in optimized builds. Unit-test assertions are separate from those production gates.

## Selected presentation libraries

[ADR-0096](../../docs/adr/ADR-0096-select-reusable-rust-cli-presentation-libraries.md) accepts focused libraries behind shared presentation components. The runtime baseline is declared in this package, insta is a development dependency, and clap_complete/clap_mangen belong to the private xtask. The optional `rich-diagnostics` Cargo feature includes miette. Default builds omit it, while the all-features checks above compile it.

The [Rust Standards library reference](../../.agents/skills/inframeld-rust-standards/references/cli-libraries.md) owns the responsibility map and deferred alternatives. Manifests and Cargo.lock own exact versions and features. Dependency availability does not implement prompts, snapshots, completion/manual generation or product-command output. Offline version JSON has its own implemented consumer and bounded contract.

<a id="proposed-command-and-presentation-organization"></a>

## Command and presentation organization

[ADR-0097](../../docs/adr/ADR-0097-organize-rust-cli-by-command-family-and-typed-results.md) accepts command-family modules within one CLI package, command-local clap declarations and typed results before shared reporting. The [Rust Standards structure reference](../../.agents/skills/inframeld-rust-standards/references/cli-structure.md) explains placement through a worked declaration and the end-to-end lifecycle flowchart. [Application Contracts' presentation reference](../../.agents/skills/inframeld-application-contracts/references/cli-presentation-components.md) owns reusable components consuming the accepted output/result contracts. Offline version and target commands implement JSON, final-only JSONL and descriptive dry-run. Target preferences also have typed Current/Proposed and confirmed Before/Now views with bounded terminal styling. Other command families, general progress/warning presentation and pagination remain separate work. This supporting feature does not complete #158.

## Stateless server discovery

The library's `discovery::discover` validates one exact HTTPS API identity without accessing credentials, saving targets or starting browser login. It uses the generated application SDK for RFC 9728 metadata and the maintained OpenID Connect library for the advertised Hydra provider. `DiscoveryOptions` supports additional trusted CA certificates and an explicit proxy. Proxy environment variables are not read implicitly. Public errors retain safe categories rather than raw upstream text.

Start reading at [`src/discovery/mod.rs`](src/discovery/mod.rs), which preserves the public interface and keeps managed-local context fields private. The operation lives in `discover.rs`, installation records and provider validation in `installation.rs`, URL decisions in `url_policy.rs`, provider HTTP adaptation in `oidc_transport.rs` and safe failures in `error.rs`. Transport scenarios remain together in `transport_tests.rs`, while pure URL tests live beside their policy. This split follows responsibilities rather than requiring identical layer folders for every capability.

Discovery allows ten seconds overall, five per request and 64 KiB per response, with redirects and retries disabled. The internal managed-local context has no public constructor or deserialization path. Its origin/installation checks are tested with controlled trusted context. Actual managed-runtime ownership remains #162. The target commands below own persistence. Login remains #160. The [server discovery guide](../../docs/development/guides/server-discovery.md) describes the wire profile and operator setup, with [manual inspection steps and their limits](../../docs/development/guides/server-discovery.md#manually-check-the-current-delivery).

## Register and select credential-free targets

Use `target add LABEL --url HTTPS_URL` to validate public API, issuer and signing-key metadata and save a connection. Registration does not select it. `target use LABEL` explicitly saves the global preference. `target show` reads the effective registered target using `--target`, then `INFRAMELD_TARGET`, then the saved preference. An explicit override never changes saved state. `add` and `use` reject a competing `--target`. Unknown or invalid effective values fail without falling back.

The [user guide](../docs/src/app/guides/register-a-target/page.mdx) covers the real commands, explicit CA/proxy inputs and failure recovery. They never load an account or credential, open a browser, select a Project or grant access. The common output contract is implemented only for these commands and offline version. Broader #158 behavior remains open.

The schema version 1 JSON registry is `$XDG_CONFIG_HOME/inframeld/targets`, or `$HOME/.config/inframeld/targets` when the variable is unset. A configured root must be absolute. The CLI does not read `.env` or search the working directory. The registry is bounded to 4 MiB, its directory is private 0700 and files are 0600. Malformed, unsupported, symlinked or insecure state is rejected without rewriting it. A separate `targets.lock` inode provides a kernel writer lock, with a two-second acquisition budget and 25 ms waits. Its presence alone does not indicate a live writer. Writers reload current state under the lock and publish a same-directory temporary file through file sync, atomic replacement and directory sync. Discovery runs outside that lock. A post-publication error retains the actual file and reports uncertainty.

Labels use 1-64 ASCII letters/digits/dots/underscores/hyphens, starting with a letter or digit, and compare exactly. A label cannot replace a different installation/API/issuer/client/transport binding. Repeating an identical registration after successful discovery reports `alreadyRegistered`. No reconfiguration, target deletion, credential store or config-revision framework is delivered.

`--ca-cert FILE` accepts up to 8 public PEM bundles of 256 KiB each. Only absolute operator-managed references are stored. Each network attempt reads their current contents once and uses that parsed snapshot throughout discovery. File or symlink changes affect the next attempt. Missing/invalid configured CA data fails instead of being omitted. `--proxy URL` accepts one explicit credential-free HTTP(S) origin. User information, queries, fragments and non-root paths are rejected. Ambient proxy settings remain disabled. HTTPS validation, discovery deadlines and exact original API/issuer spelling remain unchanged. Entered HTTP URLs do not create managed-local trust.

All target commands support human output, one final JSON object or explicit final-only JSONL, and descriptive dry-run. Dry-run validates the supplied local inputs and registry without discovery or writes. `show` labels its result `savedBinding`, without claiming current reachability or permission. `use` reports when an environment value continues to override the saved preference. INT/TERM produce130/143 and preserve confirmed local effects. A blocked or interrupted final output can be incomplete. Read `target show` before repeating a save with an uncertain result.

### Manually check target registration and selection

Prerequisites: build this source with the pinned toolchain, have an operator-supplied exact public HTTPS API identity, compatible enabled discovery and issuer configuration, network/VPN access and the required trusted CA. These are credential-free checks. No account, token, private admin access or seed operation is required. A complete engineering walkthrough against an operator-configured installation is separate from controlled local TLS tests and must precede human handoff in #185. #298 covers a different repair/proof journey.

From the repository root, build the actual executable:

```sh
cargo build --locked -p inframeld-cli
```

Use a disposable test shell for this recipe. Set `api_url` to the operator's exact API identity, replacing the example. Create one disposable configuration root and clear the inherited target selector so bare readback uses the saved preference. Keep the same variables for every command below:

```sh
api_url='https://api.dev.example.com'
target_config_root="$(mktemp -d)"
unset INFRAMELD_TARGET
XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target add dev --url "$api_url" --dry-run --json --no-input
XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target show --target dev --json --no-input
```

The dry-run exits 0 with `remoteVerification: "notPerformed"`. The inspection exits 1 with `target_not_found`, because preview did not save a target. If the installation needs a private CA or proxy, add the actual `--ca-cert`/`--proxy` inputs to both registration invocations. Preserve the operator's CA file during cleanup.

Run registration and inspect it explicitly before selecting it:

```sh
XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target add dev --url "$api_url" --json --no-input
XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target show --target dev
XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target use dev --json --no-input
XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target show --jsonl --no-input
```

Each exits 0 on success. Registration returns `registration: "saved"` and `selectionChanged: false`. Explicit readback shows the same installation/API/issuer. `use` reports `savedTarget: "dev"`. The final JSONL invocation emits one result record with `verification: "savedBinding"`. No sign-in or Project state is created. Repeating the identical registration reports `alreadyRegistered`.

Check precedence and safe rejection:

```sh
INFRAMELD_TARGET=missing XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target show --target dev --json
INFRAMELD_TARGET=missing XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target show --json
XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target add local --url http://127.0.0.1:9 --json
XDG_CONFIG_HOME="$target_config_root" target/debug/inframeld target show --json
```

The first exits 0 using `flag` without persisting the override. The second exits 1 rather than falling back. HTTP registration exits 2 with `discovery_invalid_url`. The last readback still selects `dev` and its original binding. Compare human and machine facts, observe any environment warning, and retain only safe outputs. For interruption or uncertain persistence, inspect the saved target before repeating a change.

Remove only the disposable configuration root you created:

```sh
rm -r -- "$target_config_root"
unset target_config_root api_url
```

Record actual executable revision/platform, exact configured public identity, commands, results and cleanup separately from automated tests. If that installation is unavailable, report the walkthrough as not run and keep human preparation with engineering. A readable recipe or green unit suite is not a human acceptance result.

### Compare terminal preference views

This optional walkthrough needs an already prepared disposable configuration root with registered labels `prod` and `dev`, with `prod` saved. The registration recipe above creates only `dev`, so it does not supply this starting state by itself. Use the source-built executable from the repository root and replace the path below with that prepared root. These examples are a procedure, not a recorded operator pass.

```sh
style_config_root='/absolute/path/to/prepared-disposable-config-root'
unset INFRAMELD_TARGET
XDG_CONFIG_HOME="$style_config_root" target/debug/inframeld target use dev --dry-run
XDG_CONFIG_HOME="$style_config_root" target/debug/inframeld target use dev --dry-run --plain
XDG_CONFIG_HOME="$style_config_root" target/debug/inframeld target use dev --dry-run --json
```

The human previews show Current/Proposed, with `prod` and `dev` as the compared saved preference. They perform no network call or preference write. On eligible terminal stdout, only the unequal known values are styled: old red with strikethrough, new green. The plain and JSON forms keep the same facts without presentation ANSI. Green means new, not approved or applied.

To check a confirmed save after reviewing the preview:

```sh
XDG_CONFIG_HOME="$style_config_root" target/debug/inframeld target use dev
```

A confirmed changed save shows Before/Now from the mutation's locked observation. Preview does not reserve that state. Repeated, unknown or unconfirmed observations do not gain a colored completed-change claim. After uncertainty, use the existing readback procedure before another save. Once the change is confirmed, restore the prepared original preference with `XDG_CONFIG_HOME="$style_config_root" target/debug/inframeld target use prod`, then unset `style_config_root`. Do not delete a prepared root you did not create.

`--plain`, `--no-color`, nonempty `NO_COLOR`, `TERM=dumb` or non-terminal stdout disables this styling. `CLICOLOR_FORCE=1` overrides none of those vetoes. Empty `NO_COLOR` alone is not a veto, and `--no-input` does not disable styling. Help/version and JSON/JSONL remain unstyled. See the [target output reference](../docs/src/app/clients/cli/target-reference/page.mdx) for interpretation. Record any actual TTY exercise separately from the operator-configured HTTPS walkthrough and human acceptance in #185.

## Human recipient-proof acquisition boundary

The [approved issuer binding](../../.agents/skills/inframeld-access-models/references/decision-human-cli-issuer-binding.md) selects the next maintained acquisition path. Its single Rust capability belongs under `src/auth/`, with flow, callback, transport, recipient-proof and maintenance-handoff responsibilities. This is an allocated design, not an implemented library or executable command at this recording checkpoint. The current executable surface and discovery library described above remain unchanged. Full login persistence stays with its owning work.

The selected human/operator recipe is conditional on delivering and qualifying that capability:

1. Independently identify the managed installation and trusted target/API/issuer/client. Confirm the private-administration and no-attacker-registration/alternative-approval prerequisites. Discovery or provisioning alone cannot certify them.
2. Start the maintained Authorization Code/S256-PKCE flow. Freeze the complete attempt context and derive the callback from the exact issuer UTF-8 using full lowercase SHA-256. Bind literal `127.0.0.1` and an ephemeral port, then open the system browser against the trusted installation. The user sees the verified account and requested installation access.
3. Check the actual receiving address/port, exact Host/path, state and issuer-response policy for success or error before code exchange. Use maintained token/ID-token verification and the identical attempt redirect URI. Do not use a legacy callback fallback, scrape cookies, decode opaque access tokens or perform administrative test approval as a user procedure.
4. Keep the transient access token in protected memory and deliver it directly to the separately authorized maintenance command's protected stdin. Never put it in arguments, logs, token files or a business-client fallback. Host authority, installation binding and fresh server-side recipient eligibility remain mandatory.

No copyable acquisition command is available yet. The account UI and rendered human/operator journey still need implementation and qualification, including two-issuer failures, denied/error callbacks, cutover and credential-chain preservation. Existing private-provider test approval and server-side verifier evidence do not close that gap. [Host maintenance](../../.agents/skills/inframeld-access-models/references/host-maintenance.md#maintenance-wire) owns the protected request and replay contract. [ADR-0125](../../docs/adr/ADR-0125-bind-human-cli-callbacks-to-their-issuer.md) records the narrow callback decision without changing product admission or repair authority.
