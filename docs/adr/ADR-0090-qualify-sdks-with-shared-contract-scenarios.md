# ADR-0090: Qualify SDKs with shared contract scenarios

> **Subsequent promotion:** [ADR-0091](ADR-0091-promote-selected-sdks-and-retire-generator-comparisons.md) promotes the selected packages, implements shared conformance and retires alternative implementations and comparison reproduction. The context and evidence below describe the original decision.

**Status:** Accepted design. Unified three-SDK execution, automatic operation coverage and required SDK CI gates await implementation.

**Date:** 2026-10-27. The developer approved recording the shared qualification strategy as accepted design on this date.

## Context and Problem Statement

Alice adds an operation with an optional nullable field. One SDK serializes omission as null. A shared scenario must expose that failure in that SDK even if the other clients pass. Matching SDK outputs alone is insufficient because multiple clients can share the same defect.

TypeScript and Python already share a scenario/assertion harness and backend witnesses. Rust uses the same controlled backend factory but retains separate scenarios and assertions. Existing SDK workflows are manually dispatched comparisons. Their passing local evidence does not establish a required all-language delivery gate.

## Considered Options

- Share authored scenarios and expectations, with native language drivers and complementary model/type checks.
- Maintain independent per-language suites, accepting duplicated assertions and the risk that expected behavior diverges.
- Generate HTTP-only schema checks. These can demonstrate backend contract behavior but do not exercise the generated SDK methods/models.

Schema-driven inputs can supplement authored cases, but cannot invent business expectations from OpenAPI alone.

## Decision Outcome

Use common scenarios and assertions for the selected Rust, TypeScript and Python SDKs. Each small native driver constructs generated models, invokes generated methods and exposes only available SDK observations. Test real production HTTP routers with controlled collaborators and isolate mutable fixture state between clients/scenarios.

Use backend witnesses for received encoding, multipart bytes and dispatch counts. Inspect native typed results/errors and available response metadata separately. Drivers cannot repair requests, fabricate metadata, reconstruct replacement typed errors or issue fallback/repeated HTTP operations.

The target coverage gate compares delivered OpenAPI operations with meaningful scenario sets and native bindings. Missing coverage or bindings fail. Keep compilation, native model/type tests, HTTP behavior, fresh regeneration/drift and external consumption distinct. Collect independent SDK results and require every expected runtime/scenario exactly once. Record real platform constraints explicitly rather than silently skipping a failing SDK.

Once implemented, selected SDK checks become required for applicable delivery changes. Historical upstream/alternative comparisons retain separate experimental jobs and their expected failures. New shapes and protocols need their own cases, including changes within an existing operation ID.

The [SDK qualification reference](../../.agents/skills/inframeld-sdks/references/shared-qualification.md) owns this workflow and its implementation boundary. [Testing](../../.agents/skills/inframeld-testing/SKILL.md) owns general layer selection/isolation/evidence, Coding Standards owns TDD/code conventions, and domain skills own business meaning.

## Consequences

- Endpoint delivery adds one shared scenario set and small native operation bindings rather than three independent expectation sets. Language-specific checks remain where languages enforce guarantees differently.
- A red result requires investigation of stale generation, missing seams, backend/fixture mismatch or generator defects. It does not automatically authorize a generator patch or weakening the backend contract.
- Preserve the regression when a verified generator source/resource fix resolves a defect, including after an upstream fix retires the patch.
- Existing separate runners remain usable. Report missing unified coverage honestly until dedicated implementation delivers the accepted gate. This decision changes no runner, workflow, branch protection or command.
- SDK adapter tests with doubles do not establish real database/provider behavior, durable jobs, receipts or full product journeys. Synthetic Rust capabilities are not inherited by another language.
- This records design rather than new qualification evidence or public-release compatibility. No remote CI dispatch or external mutation follows from loading its guidance.

## Links

- [Shared SDK strategy](../../.agents/skills/inframeld-sdks/SKILL.md), [generator maintenance](../../.agents/skills/inframeld-sdks/references/generator-maintenance.md), and [test strategy](../../.agents/skills/inframeld-testing/references/test-strategy.md).
- [ADR-0055](ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md), [ADR-0088](ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md), and [ADR-0089](ADR-0089-select-patched-typescript-and-python-sdk-generators.md).
- [Available Rust runner](../../packages/sdk-tools/drivers/rust/src/main.rs), [available language runner](../../packages/sdk-tools/src/workflows/test.ts), and [controlled backend](../../apps/backend/tests/support/sdk_conformance_app.py).
