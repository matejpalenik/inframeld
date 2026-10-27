# ADR-0093: Preserve response integrity and type native SDK boundaries

**Status:** Accepted

**Date:** 2026-10-27

## Context and Problem Statement

A session response with HTTP 200 and an empty body must fail when OpenAPI declares a required object. An HTTP 204 is valid only when declared, and JSON null is valid only for a nullable response. Earlier SDK qualification missed parser shortcuts, root response nullability and lossy primitive/UTF-8 decoding. A generic `typed` observation also obscured whether a generated decoder or schema validator actually ran.

Customers and the Rust CLI will consume the generated clients. The development harness must expose SDK defects faithfully and remain understandable without concealing incorrect calls behind reflection or broad exception handling. This decision implements the developer-approved hardening plan. Qualification evidence remains a separate fact.

## Considered Options

- Retain permissive runtime shortcuts and compensate in test drivers. This would allow incorrect SDK success and conceal customer-facing defects.
- Add handwritten public transport wrappers or replace the selected generators. This broadens the public API and maintenance scope beyond the approved approach.
- Keep selected generator versions and patch verified source/resources, with stricter native response handling and typed driver boundaries.

## Decision Outcome

Retain the selected generators and the architecture in ADR-0092. Generate TypeScript response-selection metadata alongside validators. Select exact status before declared class/default, check representation/body presence, and validate successful buffered JSON even on empty paths. Nullable and bodyless responses stay distinct. Reject malformed JSON and invalid UTF-8 instead of converting them into success. Native JSON/model decoding must not coerce invalid primitive values to the required type.

Python detailed responses preserve HTTPX `Headers`, retaining indexed/get access and repeated values. Their JSON representation emits ordered name/value pairs. Exceptions retain available exact response bytes separately from convenient decoded text and preserve decoding causes. Rust observations use native error bytes rather than lossy text. Fetch raw error content remains its exposed text rendering, with browser restrictions preserved.

Private protocol version 2 records validation provenance and body absence versus null. Drivers expose SDK success, SDK failure or driver failure. Python uses strict protocol records, direct generated calls and explicit ownership of production/fixture clients. Strict Pyright/Ruff and separate shared/native TypeScript projects check handwritten tooling and consumer programs. Generated signatures remain the actual call-site authority.

Case-scoped backend witnesses are registered, collected and deleted. Independent total dispatch counts expose retries that lose witness headers. Resource ownership bounds startup, execution, output and cleanup. Archive construction stays independent of HTTP execution, while verification composes archives, isolated endpoints and installed consumers.

## Consequences

Invalid responses now fail where earlier runtimes returned success. Native generated model types and Python response-header types become more precise. Header users relying on dictionary-only serialization must use the documented ordered JSON pairs or native HTTPX access.

Patches require retained behavioral regressions, verified inputs, explicit regeneration, drift and consumer checks. A patch retires only when its regression passes against the proposed source without it. Broader generator redesign requires reconsideration instead of recurring endpoint exceptions.

This does not publish packages, introduce public transport-construction APIs, qualify unsupported protocols or resolve server-version compatibility. Controlled HTTP evidence does not replace persistence, real identity-provider or full CLI/account journeys. A 9/10 qualification or issue-closure recommendation still requires applicable CI evidence and independent review.

## Links

- [ADR-0094: response variants, typed TypeScript failures and transport defaults](ADR-0094-select-sdk-response-variants-and-safe-transport-defaults.md) extends this decision without changing the generator choices.
- [ADR-0088: Rust generator](ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md)
- [ADR-0089: TypeScript/Python generators](ADR-0089-select-patched-typescript-and-python-sdk-generators.md)
- [ADR-0090: shared qualification](ADR-0090-qualify-sdks-with-shared-contract-scenarios.md)
- [ADR-0092: readable typed workflows](ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md)
- [Shared SDK ownership](../../.agents/skills/inframeld-sdks/SKILL.md)
- [Runbook](../../packages/sdk-tools/README.md), [patch maintenance](../../packages/sdk-tools/docs/generators.md) and [dated evidence](../development/reports/sdk-hardening-verification.md)
