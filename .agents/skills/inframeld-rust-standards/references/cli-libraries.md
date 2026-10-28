# Use the selected Rust CLI libraries

Alice lists builds in a terminal and then requests the same permitted facts as JSON in CI. The command owns those facts. Shared presentation uses existing libraries for layout, styles and progress while the approved CLI contract determines framing, interaction and outcome meaning.

> **Status:** accepted library choices on 2026-10-28, recorded in [ADR-0096](../../../../docs/adr/ADR-0096-select-reusable-rust-cli-presentation-libraries.md). The selected dependency baseline is declared in the CLI and private xtask manifests, with miette optional. Manifests and Cargo.lock own versions and features. Declared dependencies do not establish runtime presentation behavior or its qualification. The [file/module structure](cli-structure.md) is separately accepted through ADR-0097 and remains a target for implementation.

## Selected stack

Use these libraries for their selected responsibilities rather than implementing competing terminal machinery or adding another library for the same job.

| Responsibility | Selected library | Scope |
| --- | --- | --- |
| Arguments and help | [clap](https://docs.rs/clap/latest/clap/_derive/_tutorial/) | Keep typed declarations and reusable argument groups as the source for parsing and help. |
| Machine serialization | [Serde](https://serde.rs/) and serde_json | Serialize approved typed CLI results. The generated SDK response and human table cells do not define the CLI schema. |
| Typed errors | [thiserror](https://docs.rs/thiserror/latest/thiserror/) | Keep meaningful failure variants and useful safe causes. The outer command boundary owns reporting and exit conversion. |
| Semantic styles and adaptive streams | [anstyle](https://docs.rs/anstyle/latest/anstyle/) and [anstream](https://docs.rs/anstream/latest/anstream/) | Define shared styles and adapt output to the actual destination's capabilities. Terminal adaptation does not replace content sanitization or redaction. |
| Progress | [indicatif](https://docs.rs/indicatif/latest/indicatif/) | Use bars, spinners and multiple indicators through shared progress support. Provide readable nonterminal observations when needed rather than relying on hidden bars alone. |
| Human tables | [tabled](https://github.com/zhiburt/tabled) | Centralize table presets, alignment, widths, wrapping and empty views in shared human components. Commands supply meaningful typed rows and columns. |
| Interactive input | [dialoguer](https://docs.rs/dialoguer/latest/dialoguer/) | Share confirmation, selection, validation and password-input mechanics behind the invocation's interaction policy. |
| Completions and manuals | [clap_complete](https://docs.rs/clap_complete/latest/clap_complete/) and [clap_mangen](https://docs.rs/clap_mangen/latest/clap_mangen/) | Generate from the same clap declarations. Use the existing Rust xtask for development generation. |
| Presentation regression checks | [insta](https://insta.rs/docs/) | Add reviewed snapshots for meaningful human layouts alongside the existing assert_cmd, predicates and tempfile process-test support. Explicit assertions still verify JSON fields, streams, exits and effects. |

The [CLI manifest](../../../../apps/cli/Cargo.toml) declares the runtime libraries and keeps insta with the existing process-test helpers as development dependencies. The [xtask manifest](../../../../apps/cli/xtask/Cargo.toml) declares clap_complete and clap_mangen for development generation. The CLI's optional `rich-diagnostics` Cargo feature enables miette with derive support and rich reports without backtrace capture.

The baseline is available for the owning features to consume. Keep additional dependency features tied to concrete needs and preserve the pinned toolchain and strict checks. Availability does not implement components, prompts, snapshots, completion/manual generation or public JSON output. Manifests and Cargo.lock remain the version and feature source of truth.

## Conditional diagnostics and deferred alternatives

Use [miette](https://docs.rs/miette/latest/miette/) when user-authored configuration or import content needs source-aware diagnostics, such as a labelled invalid field. Route its human reports through the shared output boundary. It does not define the product's JSON error shape or authorize displaying protected source content.

The accepted default remains tabled and dialoguer. The reviewed alternatives are not additional defaults:

- [comfy-table](https://github.com/Nukesor/comfy-table) provides convenient automatic width allocation. Its README currently records continued maintenance, a feature freeze and a search for a maintainer.
- [inquire](https://docs.rs/inquire/latest/inquire/) offers richer typed prompts, autocomplete and optional date selection. Revisit only when a concrete need exceeds the selected prompt support.
- [cliclack](https://docs.rs/cliclack/latest/cliclack/) is an option for a deliberately designed onboarding wizard, rather than a second general output system.
- [iocraft](https://docs.rs/iocraft/latest/iocraft/) offers declarative components and layouts. Its documented unstable custom-stream support and terminal operations that can bypass a supplied writer need qualification before any render loop shares the CLI's machine channel.
- [Ratatui](https://ratatui.rs/) remains an option for an explicitly scoped future interactive terminal application. No fullscreen UI is selected for ordinary commands.

These observations explain the choice. Recheck current primary documentation when reconsidering a dependency rather than treating a maintenance snapshot as permanent.

## Keep product policy with its owner

[Application Contracts' presentation reference](../../inframeld-application-contracts/references/cli-presentation-components.md) owns component responsibilities and links the accepted output, outcome, interaction and change-review contracts. Libraries implement mechanics under those contracts. Presenters perform no SDK requests, credential refresh or retry decisions.

Keep command-specific meaning explicit while sharing real formatting decisions. Avoid a generic command framework, a universal document tree or a trait for each visual primitive solely to integrate these libraries. The [accepted module layout](cli-structure.md) owns placement and the invocation lifecycle. Library selection and structure acceptance do not themselves authorize application refactoring.

Qualify the actual integration through meaningful behavior, including narrow widths, plain output, controlled failures, terminal text, interaction cancellation and stdout/stderr separation where relevant. Documentation and dependency selection alone establish none of those runtime guarantees.
