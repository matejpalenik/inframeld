# CLI foundation verification

Recorded 2026-10-28 in Europe/Prague. Work remains on issue/157, based on revision 14b000f6a19995d384d23e199be1e48e805f8736. Current artifacts explicitly report sourceDirty=true. Their revision identifies the checkout base, not a committed final delivery revision.

## Rust tooling replacement

The Python archive helpers and shell packaging driver have been replaced by the private Rust xtask. Local packaging and the four-platform CI workflow call the same cargo xtask package command. Production qualification uses explicit Result errors, with no assertions or debug assertions that optimization could remove.

The checked-in compatibility descriptor owns policy fields. Cargo supplies the version. The build script generates revision, target and dirty-source identity into one metadata document. CLI version output, archived metadata and native verification use that same document. The verifier rejects false release claims before executing the bundled binary and compares the binary's output against the exact archived metadata.

## Checks personally run for this revision

| Check | Result |
| --- | --- |
| Scaffold-first archive, metadata, tool-prerequisite and installation tests | Intended behavioral failures observed before implementing the affected behavior |
| Unexpected user-file regression | Intended failure observed, then complete user-state snapshot verification implemented |
| Rust formatting and strict Clippy for CLI and xtask | Passed |
| CLI integration tests | Seven passed, covering offline help, read-only home, usage failures, SDK behavior and compatibility metadata |
| xtask integration tests | Eight passed, covering normalization, corruption, wrong targets, false release claims, overwrite refusal, user-state preservation, evidence mismatch and missing tooling |
| Release-mode qualification regression suite | Five passed. Rejection gates remain active under optimization |
| Rustdoc with warnings denied | Passed for CLI and xtask |
| cargo-deny 0.20.2 | CLI and xtask advisories, bans, licenses and sources passed |
| pnpm check | Passed, including uncached CLI/xtask checks. Some unchanged backend/web/tooling results came from Turbo cache |
| pnpm build | Passed. CLI/xtask built, unchanged other packages used cache |
| Complete SDK verification | Initial run failed two existing Rust loopback lifecycle tests with IncompleteMessage. All other stages passed. The isolated lifecycle rerun passed five tests. The complete repeat passed all Rust, TypeScript and Python stages |
| cargo xtask package --reproducible | Passed locally on native Apple Silicon, with forced CLI recompilation between builds |

The first complete SDK failure is retained rather than reclassified as success. The subsequent unfiltered pnpm sdk:verify run completed successfully with partial=false. No SDK source or transport setting was changed to bypass it. Its precise transient cause has not been established. Earlier complete verification passed during the Python-backed foundation iteration, but that historical result does not replace current verification.

## Native artifact and reproducibility evidence

Environment: macOS 26.3.1 ARM64, Rust 1.95.0, cargo-dist 0.33.0. No Python is used by CLI packaging, testing or native CI qualification. The separate backend and cross-language SDK tooling retain their own Python requirements.

The native task passed checksums, payload validation, permission-denied installation, overwrite refusal, blocked destinations, paths with spaces, executable invocation and removal. It compared the complete temporary user's file state before and after. Archive reads reject unsafe/duplicate paths, links, unexpected payloads and oversized inputs. Child-process waits are bounded.

Two builds using the same source inputs, pinned toolchain, source-path remapping and source epoch produced identical normalized archive bytes, executable bytes and typed evidence:

- Target: aarch64-apple-darwin
- Archive SHA-256: 6d20aefa43f8af264f71183ddc5f9b89c8653f30514f00ff2e07aaabfb2428b8
- Executable SHA-256: a4a19937c4941f21e9224fb2623a149b2959d4d57146fa72b6abced416bb4ef6

This establishes repeated-build equality in this environment. It does not establish cross-host bit reproducibility or release compatibility.

## Remaining qualification

The workflow configures native Apple Silicon and Intel macOS 15, plus x86-64 and ARM64 Ubuntu 22.04. No remote workflow was dispatched. Those CI executions remain pending. The macOS 13 deployment flag is a build constraint and is no longer advertised as a qualified minimum supported OS. Local evidence covers macOS 26.3.1 only.

No release/tag, registry package or branch-rule setting was published. The development CLI remains version 0.0.0 and qualifies no released runtime pair. Full issue closure still requires the remote native matrix and final committed-revision evidence. Login, product commands, JSON automation and remote version enforcement retain their owning delivery boundaries.

## Historical evidence and guidance

The earlier Python-backed iteration passed repository checks, complete SDK verification and two normalized native archive builds. Review subsequently demonstrated that Python optimization disabled assertion-based qualification checks. That implementation has been removed, with debug and release-mode Rust regressions covering the defect. The original raw cargo-dist timestamp/ownership reproducibility defect remains covered by Rust normalization tests.

The ADR-0095 policy and its owning skill references remain accepted. Updated CLI directory guidance and development instructions route maintainers to the shared Rust task. The final Markdown check inspected 685 local targets with no missing files. Workflow YAML parsed successfully. Fresh skill-activation trials were not performed.

## Selected dependency baseline revalidation

The selected ADR-0096 libraries are now declared in the CLI and xtask manifests. The CLI owns terminal styles/streams, tables, progress and prompts. Insta is a development dependency. Completion/manual generators belong to xtask. Miette is optional behind the rich-diagnostics Cargo feature, with derive support and rich reports without backtrace capture.

Cargo.lock adds 48 packages without removing or changing an existing locked package version. This makes the libraries available. It does not implement the ADR-0097 source migration, shared presentation components, completion/manual generation or product automation.

The following checks were personally rerun after the dependency change:

| Check | Result |
| --- | --- |
| Locked CLI/xtask check with all targets and all features | Passed, including optional miette |
| Rust formatting and strict Clippy with all targets/features | Passed |
| CLI and xtask integration tests with all features | Fifteen passed, seven CLI and eight xtask |
| Optimized xtask qualification tests | Five passed |
| Rustdoc with warnings denied and all features | Passed |
| Default-feature CLI and xtask build | Passed |
| cargo-deny 0.20.2 for both manifests | Advisories, bans, licenses and sources passed |
| Native Apple Silicon packaging with forced repeated compilation | Passed, including installation/removal and complete isolated user-state checks |

The first sandboxed test invocation could not bind its isolated localhost listeners and failed with Operation not permitted. The full rerun outside that sandbox passed without test or application source changes. Dependency audits retained the configured warnings for multiple syn majors and, in the CLI all-features graph, multiple unicode-width majors. No policy exception or weakened gate was added.

### Updated local artifact evidence

The earlier archive hashes in this report precede the selected dependency baseline. This new native run used macOS 26.3.1, Rust 1.95.0 and cargo-dist 0.33.0. Its first and second typed evidence documents were equal:

- Target: aarch64-apple-darwin
- Archive SHA-256: 7c87e20adab9afa3d66b0bc1c6be7e08ded09d26a1bd60aae852e1c7078019b0
- Executable SHA-256: eed6ddcbff947b7918753723224b5bbcaaf54c1b643c229d3e8fdb3e65bd2363
- Compressed archive size: 265984 bytes
- Source revision: 14b000f6a19995d384d23e199be1e48e805f8736
- Source dirty: true
- Permission-denied installation checked: true

This is repeated-build equality for the local development worktree. It remains neither final committed-revision evidence nor qualification of another platform or released runtime pair. Complete SDK verification and full repository checks were not rerun for this dependency-only step. Their earlier results above retain their original scope.

The native CI matrix and final committed-source evidence remain required for issue #157. The compatibility decision is accepted locally through ADR-0095, while the GitHub issue still carries its older needs-decision label. Reconcile that tracking when publishing the accepted work. General JSON/dry-run contracts and implementation remain #156/#158, with login and target selection in their owning issues.
