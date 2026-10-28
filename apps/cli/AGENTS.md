# Rust CLI guidance

Read the shared [Coding Standards](../../.agents/skills/inframeld-coding-standards/SKILL.md) and [Rust Standards](../../.agents/skills/inframeld-rust-standards/SKILL.md) before code planning, suggestions or review. This package is a presentation adapter using clap and the generated `inframeld-sdk`. Backend domains retain permissions, state and retry policy.

The [accepted CLI structure](../../.agents/skills/inframeld-rust-standards/references/cli-structure.md) owns command-family modules, command-local clap declarations, typed results and the lifecycle diagram under ADR-0097. [Shared presentation components](../../.agents/skills/inframeld-application-contracts/references/cli-presentation-components.md) owns reusable human presentation responsibilities. Both distinguish accepted targets from implemented behavior. Exact JSON, dry-run and per-command outcome mappings remain their owning specification work. Do not infer missing wire fields or runtime support from these diagrams or examples.

For presentation dependencies, follow Rust Standards' [selected CLI libraries](../../.agents/skills/inframeld-rust-standards/references/cli-libraries.md), accepted through ADR-0096. Add them with the features that use them. ADR-0097 separately accepts the target layout. Neither decision establishes implemented behavior or authorizes application edits by itself.

Use the pinned toolchain and package checks documented in the [CLI guide](README.md). The CLI and xtask manifests retain their strict compiler/Clippy rules and generated SDK sources retain generator-owned settings. Core and Rust Standards own testing, error and documentation conventions. Do not add code-layout or composition enforcement tests.

The private xtask owns CLI packaging and qualification. Local commands and CI use that same implementation. The checked-in compatibility descriptor and generated Cargo build metadata are the sole source for human version output, archived metadata and qualification evidence. Preserve that existing tooling boundary while public product commands arrive separately.
