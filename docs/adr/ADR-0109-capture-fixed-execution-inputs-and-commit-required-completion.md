# ADR-0109: Capture fixed execution inputs and commit required completion

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

Alice starts a question using saved configuration 17. Bob saves configuration 18 while it runs. Separately, Production may serve a ready version using configuration 16. The application must keep each execution's chosen meaning and distinguish a ready build from permission to publish it. If an answer response is lost, a retry must not buy another answer.

## Considered Options

- Use the focused bounded contract above. Selected.
- Pass complete immutable inputs between stages, requiring larger messages and explicit recovery projections.

## Decision Outcome

Apply the [complete accepted PD-PIPELINES-01 contract](../../.agents/skills/inframeld-pipelines/references/decision-execution-build-receipt-contracts.md#approved-resolution). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use one durable capture identity with complete bounded application-owned projections, rather than passing mutable working settings between stages or introducing another generic executor. The capture fixes Project/Pipeline, originating saved revision or ready PipelineVersion, supported explicit overrides and complete effective settings/fingerprint, exact CollectionRevisions/DocumentVersions and processing/embedding profiles, originating principal/scope, parent operation and server-owned purpose. Large inventories use immutable paged references. Connection IDs and admitted access-revision preconditions are recorded, not executable historical connection configurations or raw credentials.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Because stages resolve one fixed capture, concurrent edits cannot retarget the operation. Because required attribution commits before success, feedback and recovery refer to an established outcome. The cost is durable capture/progress and explicit failure handling. Passing complete immutable values everywhere could also preserve meaning, but duplicates larger messages and makes crash recovery harder. A full-answer replay cache would add a different privacy and retention contract already outside v 1.

Alice's captured query keeps configuration 17 while Bob saves 18. Indexing prepares the exact bindings chosen for Alice. A live question against Production instead records its actual ready version and routing cohort. If its answer is generated and the required receipt commits, but the response is lost, retry returns that receipt without the answer and without another charge. If required receipt persistence fails after generation, the result is a local failure/uncertainty, not permission to generate again.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-pipelines/references/decision-execution-build-receipt-contracts.md#approved-resolution)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
