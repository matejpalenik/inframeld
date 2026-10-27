# ADR-0091: Promote selected SDKs and retire generator comparisons

**Status:** Accepted. Supersedes retention of experimental candidates and package identities in ADR-0088/ADR-0089, and delivers the shared conformance direction of ADR-0090. Generator selections are unchanged.

**Date:** 2026-10-27. The developer approved this implementation plan, removal of alternatives, normal package identities and Linux PR/macOS upgrade qualification on this date.

## Context and Problem Statement

Alice adds an operation with an optional nullable field. The selected SDKs should be regenerated and checked against one expectation set. A default command that evaluates rejected generators adds noise, duplicated Rust assertions can drift from other languages, and experimental package identities obscure the SDKs we intend to use.

The original comparison provides dated evidence for selecting pinned patched generators. Keeping every alternative and its tooling indefinitely has a maintenance and dependency cost. Shared conformance was already accepted, but its implementation was separate from selecting generators.

## Considered Options

- Remove unselected implementations and comparison tooling, retaining dated reports/results without promising full comparison reproduction.
- Keep an inactive reproducible archive or an active optional baseline workflow. Both preserve more code and dependencies.
- Promote normal package/import identities now, or retain generator-specific experimental names until later release work.
- Require Linux and macOS on every applicable PR, or use Linux PR checks with macOS for generator changes and manual qualification.

## Decision Outcome

Promote the selected complete clients to the language package roots. Use Rust `inframeld-sdk`, TypeScript `@inframeld/sdk`, and Python distribution `inframeld-sdk` importing as `inframeld_sdk`. Keep version 0.0.0 and publication protection. No registry name availability or release compatibility is implied.

Keep verified source patches and generator versions unchanged. Native OpenAPI remains authoritative. Production distributions exclude generated test fixtures, drivers and generator dependencies. Ordinary builds use included source and native manifests.

Use one private SDK tooling package, shared scenario catalogue/oracle and thin native drivers for Rust, TypeScript Node/Chromium and Python sync/async. Require operation coverage and complete expected profile/scenario results. Witness actual received requests separately from native SDK results. No driver serialization repairs, fabricated metadata or fallback HTTP client is permitted.

Automatic applicable PR/main checks run on Linux. Generator/patch/configuration changes also require macOS, with manual runs available. A stable aggregate validates job outcomes and complete evidence artifacts. External branch rules must separately require that check. Workflow availability does not establish executed platform evidence.

Remove rejected candidates, obsolete comparison branches/commands, dependency sets and workflows. Preserve original reports and structured measurements with an explicit retirement notice. Historical source paths and commands no longer provide reproduction. Do not invent historical Git commits for material that was uncommitted.

## Consequences

- Endpoint delivery has one authored expectation set and native bindings. Native model/type and synthetic capability regressions retain their separate evidence boundaries.
- Missing bindings, incomplete profiles, unexpected results, decoding failures and unavailable required runtimes fail visibly. Independent SDKs still execute after another fails.
- Generator upgrades remain deliberate verified maintenance. Retain regression coverage after patch retirement. Rust metadata-disabled compatibility is checked through a generated consumer contract, while its original byte-identical baseline comparison remains historical evidence.
- Local package consumption and later CLI integration use meaningful names, with one intentional local import/path migration and no compatibility aliases for the retired candidates.
- Full alternative-generator reproduction is intentionally retired. Future reconsideration requires a new evidence-gathering task rather than silently restoring historical candidates.
- SDK fixtures do not prove real database/provider behavior or complete CLI/account-UI journeys. Public release policy, server-version compatibility and unsupported protocols remain separate work.

The subsequent [ADR-0092](ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md) replaces the tooling organization and test execution mechanics. Package promotion, generator rationale and comparison retirement remain unchanged.

## Links

- [ADR-0088: Rust selection](ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md), [ADR-0089: TypeScript/Python selection](ADR-0089-select-patched-typescript-and-python-sdk-generators.md), and [ADR-0090: Shared conformance](ADR-0090-qualify-sdks-with-shared-contract-scenarios.md).
- [SDK policy](../../.agents/skills/inframeld-sdks/SKILL.md), [shared qualification](../../.agents/skills/inframeld-sdks/references/shared-qualification.md), and [Testing](../../.agents/skills/inframeld-testing/SKILL.md).
- [Permanent runbook](../../packages/sdk-tools/README.md), [runner](../../packages/sdk-tools/src/cli.ts), and [workflow](../../.github/workflows/sdk-conformance.yml). Consult execution artifacts for actual results.
