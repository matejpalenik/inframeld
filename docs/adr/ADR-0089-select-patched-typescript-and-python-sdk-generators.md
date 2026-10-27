# ADR-0089: Select patched TypeScript and Python SDK generators

> **Subsequent promotion:** [ADR-0091](ADR-0091-promote-selected-sdks-and-retire-generator-comparisons.md) promotes the selected packages, implements shared conformance and retires alternative implementations and comparison reproduction. The context and evidence below describe the original decision.

**Status:** Accepted. Selects language-specific implementations of the native generated-client direction.

**Date:** 2026-10-27. The developer approved both generator selections and recording them as accepted design on this date.

## Context and Problem Statement

Alice needs a generated SDK that validates a received session, preserves omitted nullable fields and retains HTTP context when decoding fails. Type annotations and successful compilation alone do not establish those behaviors. A generator can need a small reusable fix while remaining less costly than maintaining every HTTP method ourselves.

The dated TypeScript/Python comparison evaluates native OpenAPI without a schema downgrade or handwritten HTTP fallback. It separates source compilation, model/type checks, wire behavior, regeneration and external consumption. The report supplies measured evidence and its limits, including unrun remote CI and upgrade rehearsals.

## Considered Options

- TypeScript: Hey API Fetch with generated Zod validation, Orval Fetch with Zod, OpenAPI Generator Fetch, and openapi-typescript with openapi-fetch.
- Python: OpenAPI Generator HTTPX/Pydantic, openapi-python-client HTTPX/attrs, and Hey API Python.
- Retain targeted generator fixes where qualified, or require unmodified upstream output. Three isolated patch experiments were measured. Possible additional integrations or fixes are not counted as passing implementations.
- Use one generator brand across languages. Language-specific correctness and maintenance evidence do not justify that constraint.

Rust's already selected implementation remains under ADR-0088 and is not reopened by this comparison.

## Decision Outcome

Select Hey API for TypeScript with Fetch fields results, nonthrowing error mode, generated Zod success-response validation and the raw-failure-body source-asset patch. Select OpenAPI Generator for Python with HTTPX, Pydantic models and built-in resource fixes for boolean enums, field absence and decoding-error HTTP context.

Use the existing patched experimental candidates rather than renaming packages. Current versions, configuration and original archive/patch identities remain authoritative in the machine inputs linked from the runbooks. Selection does not make every configurable mode qualified. TypeScript's other response/error-validation modes and Python's broader event-loop/concurrency promises retain their recorded limits.

Maintain complete generated clients from native OpenAPI with verified targeted patches applied before generation. Ordinary SDK builds consume included source. [The SDK skill](../../.agents/skills/inframeld-sdks/SKILL.md) owns common maintenance policy, and the TypeScript/Python skills own language-specific usage and maintenance. HTTP semantics and compatibility remain with Application Contracts.

## Consequences

- The selected configurations pass the recorded contract/model and consumer checks with focused fixes. No unmodified candidate passes every recorded correctness gate.
- TypeScript includes a runtime validator dependency. Python has a larger Pydantic dependency set and Java generation tooling, without Java in the distributed Python runtime.
- openapi-python-client's multipart/metadata fixes do not resolve its unchecked scalar casts. Adding a broader validation system was not selected over the smaller observed Pydantic generator fixes.
- Keep pinning, regression coverage, source verification and explicit upgrade/retirement review. Upstream contributions are not required. Repeated endpoint-specific exceptions or broad redesign trigger reconsideration.
- Preserve all baseline results and unpublished package protections. Public names, registry release, CLI/login implementation, an HTTP escape hatch and server-version compatibility remain separate work.
- Shared all-language qualification is accepted separately in ADR-0090. Its missing runner/required-CI implementation is not supplied by this documentation decision.

## Links

- [ADR-0055: CLI-first native generated clients](ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md), [ADR-0088: Rust selection](ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md), and [ADR-0090: Shared qualification](ADR-0090-qualify-sdks-with-shared-contract-scenarios.md).
- [TypeScript skill](../../.agents/skills/inframeld-typescript-sdk/SKILL.md) and [Python skill](../../.agents/skills/inframeld-python-sdk/SKILL.md).
- [Dated comparison](../development/reports/typescript-python-sdk-generator-comparison.md), [structured evidence](../development/reports/typescript-python-sdk-generator-results.json), and [runbook](../../packages/sdk-tools/README.md).

Subsequent response-integrity and native-boundary hardening is recorded in [ADR-0093](ADR-0093-preserve-response-integrity-and-type-native-sdk-boundaries.md). This retains the generator rationale and dated qualification above.
