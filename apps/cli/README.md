# Inframeld CLI foundation

The Rust `inframeld` executable currently provides offline help and build/compatibility information. It does not start services. Login, target selection, product commands, JSON automation and descriptive dry-run remain separate delivery work (#156–#160 and their owning issues).

```sh
inframeld --help
inframeld version
inframeld version --help
```

No arguments displays help. Invalid arguments exit with code 2. Help and version require no network, configuration, credentials, Docker or writable home. The generated SDK adapter is exercised through an isolated HTTP test, not exposed as an extra product command.

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

The private pnpm wrapper integrates `@inframeld/cli` with repository lint, typecheck, test and build. CLI Turbo tasks disable caching so shared Cargo/SDK changes cannot reuse stale results. Formatting checks also include Rust. End users of archives need none of Rust, Node, pnpm or Python.

## Package without publishing

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

The command/parser and output layers handle local presentation only. Explicit connection inputs do not discover targets, enforce remote trust policy, read environment selections or establish permissions. Product application calls use `inframeld-sdk`, preserving typed errors, response metadata, bounded timeouts and disabled automatic retries/redirects. A decode or acknowledgment failure never authorizes another dispatch. Credentials, discovery and saved selections remain with #159/#160.

## Rust tooling layout

`cargo xtask package` owns the complete build, metadata stamping, normalization, checksum, installation/removal and native execution path. `--reproducible` forces a second CLI compilation and compares typed evidence. `cargo xtask verify <archive> --target <target>` checks an already normalized native archive. `cargo xtask normalize <archive> --epoch <seconds>` is the low-level normalization command. Commands are build-only and do not publish.

Archive reads reject unsafe paths, links, duplicates, unexpected files and oversized payloads. Compatibility metadata is validated before executing the bundled binary. The verifier compares its output with the exact archived metadata, exercises permission failures as an unprivileged user, and uses bounded child-process waits. Qualification failures return errors even in optimized builds. Unit-test assertions are separate from those production gates.

## Selected presentation libraries

[ADR-0096](../../docs/adr/ADR-0096-select-reusable-rust-cli-presentation-libraries.md) accepts focused libraries behind shared presentation components. The runtime baseline is declared in this package, insta is a development dependency, and clap_complete/clap_mangen belong to the private xtask. The optional `rich-diagnostics` Cargo feature includes miette. Default builds omit it, while the all-features checks above compile it.

The [Rust Standards library reference](../../.agents/skills/inframeld-rust-standards/references/cli-libraries.md) owns the responsibility map and deferred alternatives. Manifests and Cargo.lock own exact versions and features. Dependency availability does not implement shared components, prompts, snapshots, completion/manual generation or public JSON behavior.

<a id="proposed-command-and-presentation-organization"></a>

## Command and presentation organization

[ADR-0097](../../docs/adr/ADR-0097-organize-rust-cli-by-command-family-and-typed-results.md) accepts command-family modules within one CLI package, command-local clap declarations and typed results before shared reporting. The [Rust Standards structure reference](../../.agents/skills/inframeld-rust-standards/references/cli-structure.md) explains placement through a worked declaration and the end-to-end lifecycle flowchart. [Application Contracts' presentation reference](../../.agents/skills/inframeld-application-contracts/references/cli-presentation-components.md) owns reusable components consuming the accepted output/result contracts. These are accepted targets. General JSON, progress and product-command implementation and qualification remain separate work.
