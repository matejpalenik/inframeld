# ADR-0096: Select reusable Rust CLI presentation libraries

**Status:** Accepted

**Date:** 2026-10-28

## Context and Problem Statement

Alice should be able to use an Inframeld command interactively and request the same permitted facts as JSON in automation. Reimplementing table layout, terminal adaptation, prompts and progress for each command would increase maintenance and make presentation inconsistent.

The Rust CLI already selects clap, Serde/serde_json and thiserror. Existing product contracts own JSON framing, command outcomes and interaction limits. Library selection must support those contracts without turning terminal components into another policy or backend client layer.

## Considered Options

- Build terminal mechanics internally. This gives direct control but repeats layout, input and cross-platform terminal work already available in maintained libraries.
- Combine focused libraries behind shared presentation components. This preserves explicit command behavior and lets each library solve its narrow rendering or input problem.
- Adopt a broader interactive component framework such as iocraft or Ratatui as the general presentation foundation. These offer richer interactive layouts, while adding a render lifecycle and stream-integration work beyond ordinary command needs.

The review also considered comfy-table, inquire and cliclack. Their useful capabilities and selection limits are recorded in the owning library reference.

## Decision Outcome

Select focused libraries behind shared components. On this date the developer approved the reviewed recommendations and requested their documentation, while retaining file organization for further discussion.

Keep clap, Serde/serde_json and thiserror. Select anstyle/anstream, indicatif, tabled, dialoguer, clap_complete/clap_mangen and insta for their respective presentation and development responsibilities. Select miette conditionally for source-aware configuration/import diagnostics. Keep existing process-test support.

The [Rust Standards library reference](../../.agents/skills/inframeld-rust-standards/references/cli-libraries.md) owns the current responsibility map, integration guidance and deferred alternatives. Application Contracts continues to own product behavior. This decision neither accepts an exact module layout nor changes the selected generated Rust SDK boundary.

[ADR-0097](ADR-0097-organize-rust-cli-by-command-family-and-typed-results.md) subsequently records acceptance of the command-family structure and lifecycle. It leaves this library selection unchanged.

## Consequences

The CLI can share a small presentation vocabulary while delegating rendering mechanics to established crates. This adds dependency maintenance and requires qualification of their interaction with output channels, terminal capabilities, cancellation and content handling.

Adopt dependencies with the features that use them. Exact versions and features belong in manifests and Cargo.lock. Newly selected libraries have not been integrated or benchmarked by this documentation work. General presentation and command implementation remain separate delivery work.

## Links

- [Selected Rust CLI libraries](../../.agents/skills/inframeld-rust-standards/references/cli-libraries.md)
- [CLI structure and lifecycle](../../.agents/skills/inframeld-rust-standards/references/cli-structure.md)
- [Shared presentation responsibilities](../../.agents/skills/inframeld-application-contracts/references/cli-presentation-components.md)
- [CLI implementation and verification status](../../apps/cli/README.md)
- [ADR-0055: CLI-first V1 through generated clients](ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md)
