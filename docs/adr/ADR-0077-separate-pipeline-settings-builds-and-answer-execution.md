# ADR-0077: Separate Pipeline settings, builds and answer execution

**Status:** Accepted

**Date:** 2026-10-25

## Context and Problem Statement

Alice edits saved settings, tries a question and then builds a version. These operations share configuration identity but have different effects and lifetimes. Direct questions, Evaluation and production already use one ordinary execution path. The remaining choice was how to divide the owning application operations.

## Considered Options

- One broad Pipeline service exposes settings, preparation/builds and answer execution. This simplifies initial wiring but couples configuration writes, long preparation and model execution.
- Focused settings/capture, readiness-build and answer-execution capabilities share explicit fixed-input/result contracts. This makes effects and lifetimes clearer, with more explicit coordination between the parts. This is selected.

## Decision Outcome

Pipelines separates settings management/input capture, readiness builds and ordinary answer execution. The execution path is shared by direct questions, Evaluation and production serving. Pipelines owns the captured configuration/execution provenance, while Indexing owns prepared bindings and readiness of search data.

Readiness builds consume the exact authorized saved configuration and corpus captured by their owning caller. They do not follow a mutable working pointer, accept an evaluation run as configuration or turn an unsaved override into a release. Releases alone owns publication and serving selection. Reuse verified prepared data through explicit bindings rather than giving a snapshot its own executor. No Experiment resource, command bus, generic executor or workflow engine is introduced.

## Consequences

Specify capture ownership at each operation boundary, complete binding/result contracts, receipt admission/finalization and transaction/external-work handoffs before defining the concrete ports. Existing current-access, connection-change, health/pin, paid-uncertainty and receipt-only recovery rules remain authoritative. The split does not implement or qualify query/build behavior.

This records accepted target architecture. Implementation and qualification remain unfinished. Existing product decisions remain authoritative, and no earlier ADR is superseded.

## Links

- [Current owning guide and remaining design](../../.agents/skills/inframeld-pipelines/references/architecture.md#pipeline-operation-boundaries).
- [Logical records](../../.agents/skills/inframeld-pipelines/references/records.md#pipelines).
- [Module architecture](../../.agents/skills/inframeld-pipelines/references/architecture.md).
- [Application/component conventions](../../.agents/skills/inframeld-python-standards/references/component-roles-and-imports.md#component-conventions) and [modular-backend decision](ADR-0001-use-one-modular-backend-with-clear-domain-boundaries.md).
