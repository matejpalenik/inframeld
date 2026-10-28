# ADR-0095: Support matching qualified CLI and runtime releases

**Status:** Accepted

**Date:** 2026-10-27. The developer approved matching releases, metadata-first reporting and the documentation scope while planning #157, then authorized implementation.

## Context and Problem Statement

Alice installs a newer CLI while Production still runs an older runtime. Generating a client from OpenAPI establishes one contract, not compatibility with every server bearing a /v1 prefix. Repeating a write after an undecodable acknowledgment could duplicate work.

## Considered Options

- Qualify matching releases initially, keeping the supported matrix small and upgrades coordinated.
- Qualify an adjacent-release window, allowing independent upgrades at the cost of more compatibility tests and unknown-result handling.

## Decision Outcome

Support only explicitly qualified matching CLI/runtime release pairs initially. Release metadata identifies the CLI version, source revision, build target and qualified runtime release. A matching label alone is not qualification. Development builds identify themselves and claim no supported released runtime.

The CLI reports this metadata offline. Automatic remote compatibility verification requires an approved backend version contract and remains separate delivery work. Health, successful authentication, /v1 and issuer discovery do not establish version compatibility. Until that contract exists, report remote compatibility as unverified.

Generated SDK rules govern additive fields. Unknown variants, unsupported representations and decode failures fail explicitly. No such failure authorizes redispatch. Future version checks should reject unsupported pairs before effects where possible, while preserving uncertainty if admission may already have occurred.

Breaking changes require a new coordinated qualified release and explicit upgrade guidance. No compatibility window or permissive fallback is implied. Expanding support requires a new reviewed decision and evidence.

## Consequences

The first matrix is maintainable, but operators must coordinate CLI/runtime upgrades. Version metadata is support information rather than proof about a contacted server. Packaging does not publish a release or qualify the complete product journey.

## Links

- [Resolved PD-CONTRACTS-03](../../.agents/skills/inframeld-application-contracts/references/decision-cli-server-compatibility.md)
- [HTTP and generated clients](../../.agents/skills/inframeld-application-contracts/references/http-mcp-and-generated-clients.md)
- [Upgrade guidance](../development/operations/upgrades.md)
- [CLI development and packaging](../../apps/cli/README.md)

Runtime release-pair and four-platform qualification remain pending until actually executed.
