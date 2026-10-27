# ADR-0094: Select SDK response variants and safe transport defaults

**Status:** Accepted

**Date:** 2026-10-27. The developer approved typed TypeScript failures, five-second defaults and a TypeScript timeout option before implementation.

## Context and Problem Statement

Alice calls an operation that either returns a finished result with HTTP 200 or an accepted job with HTTP 202. Accepting either body's schema under either status loses the contract's meaning. Different declared JSON media types can also carry different models.

The previous TypeScript error type promised Problem Details while returning network and Zod errors without those fields. Qualified callers configured their transports carefully, but default constructors could follow redirects or omit the configured timeout. These are SDK correctness and usability problems, separate from backend domain behavior and release compatibility.

## Considered Options

- Keep TypeScript's error result but type it as unknown. This is honest but makes every caller perform its own classification.
- Return typed failure objects with validated API bodies and distinct non-API failures. The developer selected this option.
- Rely on caller signals for TypeScript timeout overrides, or add one timeout option to the existing configuration. The developer selected `timeoutMs` so cancellation does not remove the deadline.
- Leave response variants to callers or validate the representation selected by the actual status and media type. Select the latter through reusable generator patches.

## Decision Outcome

Keep the selected generator versions and verified source/resource patches. Preserve every declared JSON representation instead of flattening it before generating types and validators. Match exact status before class/default and exact media type before wildcard. Ignore media-type parameters and casing during matching. A missing content type requires an unambiguous representation. Nullable values and body absence remain distinct.

TypeScript's qualified fields result retains native `request`, `response` and raw text. Its exported `SdkFailure` distinguishes validated `api` bodies, unvalidated `http` responses, `decode` failures, `transport` failures and local `request` failures. Transport reasons distinguish network, timeout and caller cancellation. Returned error-hook values can customize diagnostic messages but cannot replace trusted classification, validated bodies, causes or HTTP context. A hook exception is a new request failure. Its aggregate cause retains the original classified failure and the hook exception, preserving the original validated body or native cause. Throwing mode throws the same classified failure. Broader response-mode qualification remains separate.

Rust's main buffered JSON method exposes a generated response enum when distinct declared representations require different models. Selection occurs before deserialization, without another request. Non-success status variants with multiple JSON models carry a generated media-payload enum. Exact bodyless declarations also precede class/default error schemas. Specialized native representation methods remain available. Python generates status/media maps and accurate success-union annotations while preserving native HTTPX headers and decoding context.

Default buffered requests use five seconds, no automatic redirects and no SDK redispatch. Rust honors generator configuration and preserves caller-supplied reqwest transports. TypeScript accepts positive finite `timeoutMs` values through client/request configuration, with a defined request override taking precedence. Its deadline combines with caller cancellation. Classification tracks the SDK deadline itself, so a caller-owned `TimeoutError` remains caller cancellation. Python default/scalar timeouts bound buffered network collection and retain native timeout exceptions. Explicit tuple overrides retain HTTPX phase-budget semantics rather than claiming a total deadline.

## Consequences

TypeScript callers must narrow the failure kind before accessing a validated API body. The packages remain unpublished at version 0.0.0. Existing server HTTP schemas do not change. These corrections do not settle release compatibility.

The Hey API shared parser is an additional explicitly verified input at its existing locked version. Preparation patches private copies of it and the generator without modifying installed dependencies. New status/media fixtures remain synthetic capability evidence. They do not qualify durable product jobs or receipts.

Retain negative and positive regressions, explicit generation, drift checks, native typing and installed consumers. Current regeneration and scoped independent reviews do not guarantee all future OpenAPI shapes. Unsupported protocols and broader streaming/concurrency promises remain separate qualification work.

## Links

- [ADR-0088: Rust generator](ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md) and [ADR-0089: TypeScript/Python generators](ADR-0089-select-patched-typescript-and-python-sdk-generators.md)
- [ADR-0092: tooling architecture](ADR-0092-maintain-sdks-with-typed-workflows-and-native-conformance-tests.md) and [ADR-0093: response integrity](ADR-0093-preserve-response-integrity-and-type-native-sdk-boundaries.md)
- [Shared SDK maintenance](../../.agents/skills/inframeld-sdks/references/generator-maintenance.md) and [qualification](../../.agents/skills/inframeld-sdks/references/shared-qualification.md)
- [SDK runbook](../../packages/sdk-tools/README.md) and [verification/review evidence](../development/reports/sdk-response-fixes-verification.md)
