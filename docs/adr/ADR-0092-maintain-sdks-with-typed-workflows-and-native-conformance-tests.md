# ADR-0092: Maintain SDKs with typed workflows and native conformance tests

**Status:** Accepted. Supersedes the SDK tooling organization and execution mechanics introduced by ADR-0091. Generator selections and comparison retirement remain unchanged.

**Date:** 2026-10-27. The developer approved this implementation plan and selected strict TypeScript, ordinary feature tests and Node's test runner on this date.

## Context and Problem Statement

Alice changes consent and needs to verify the same input across three SDKs. Previously, understanding that case required following a catalogue, a request-building switch, an assertion switch and scripts mixing generation, environment setup and HTTP execution. The SDK packages were isolated correctly, but their maintenance tooling was difficult for humans to navigate.

A review also demonstrated schema-fidelity defects and false-positive assertions. Passing operation inventories did not establish complete field fidelity. The replacement must preserve useful coverage and fix these defects without inventing another application HTTP client.

## Considered Options

- Strict TypeScript with ordinary tests, native drivers and Node's built-in runner. This reuses existing Node/browser tooling and provides checked internal boundaries.
- Python/pytest orchestration. This aligns with backend tooling but retains a Node component for generation and browser calls.
- Portable declarative JSON cases rather than ordinary TypeScript tests. These require more custom machinery for lifecycle and unusual assertions.
- Playwright Test as the shared runner. This provides richer fixtures/reports but makes all native profiles depend conceptually on a browser-oriented framework.

## Decision Outcome

Keep one private SDK tooling package organized around explicit workflows, concrete generator adapters, feature tests, native drivers, packaging and small system utilities. Use strict TypeScript, existing tsx execution and Node's standard test runner. Playwright supplies Chromium execution and isolated browser contexts.

Feature tests own inputs and visible assertions. A small registration helper supplies identity/coverage metadata without a custom test language. Real production routers with controlled collaborators independently witness requests. Native drivers call public generated APIs and return a versioned observation protocol, preserving native outcomes and available metadata without repairs or fallback requests.

Retain all five profiles and complete result/operation/binding inventories. Filtered local runs are partial and cannot satisfy full CI evidence. Preserve independent language evaluation, explicit generation, native model checks, Rust capability regressions and clean package consumers.

Fix field presence, boolean constants and explicit-null handling through targeted verified generator-input patches. Check exact expected status and meaningful request fields. No production HTTP semantics change. Existing selected generator versions, package identities and publication protection remain.

## Consequences

- Humans can locate endpoint expectations, native calls and generator maintenance without reading the entire tool. The runbook and worked walkthroughs are the starting point.
- Native model types can tighten when correcting contract violations. Runtime validation and native model evidence remain distinct from static declarations.
- Subprocesses and control requests have deadlines and cancellation. Cleanup failures remain visible alongside the original failure.
- Package identity comes from native metadata. Generation updates Rust dependencies through a parser and Python emits library source without unused repository templates.
- Standard test results, JUnit and structured observations support diagnosis. Linux/macOS job implementation and external branch-rule activation remain distinct from personally executed qualification.
- HTTP fixtures do not prove persistence atomicity, real identity providers or complete product journeys. Public transport-construction APIs, publication and SDK/server compatibility remain separate decisions.

## Links

- [SDK tooling runbook](../../packages/sdk-tools/README.md) and [architecture](../../packages/sdk-tools/docs/architecture.md).
- [Shared qualification](../../.agents/skills/inframeld-sdks/references/shared-qualification.md) and [generator maintenance](../../.agents/skills/inframeld-sdks/references/generator-maintenance.md).
- [ADR-0088](ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md), [ADR-0089](ADR-0089-select-patched-typescript-and-python-sdk-generators.md), [ADR-0090](ADR-0090-qualify-sdks-with-shared-contract-scenarios.md) and [ADR-0091](ADR-0091-promote-selected-sdks-and-retire-generator-comparisons.md).
- [SDK workflow](../../.github/workflows/sdk-conformance.yml). Actual results and platform limits belong to the verification evidence, not acceptance of this decision.
- [Local rebuild verification](../development/reports/sdk-tooling-rebuild-verification.md), including executed checks, failure probes and unrun platform limits.

Subsequent response-integrity and native-boundary hardening is recorded in [ADR-0093](ADR-0093-preserve-response-integrity-and-type-native-sdk-boundaries.md). This retains the generator rationale and dated qualification above.
