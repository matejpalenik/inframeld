# ADR-0123: Keep model metadata explicit and delete only unreferenced connections

**Status:** Accepted

**Date:** 2026-10-29

## Context and Problem Statement

A model catalogue can suggest settings without proving that a private server supports them. Separately, deleting a shared connection is safe only when no retained executable configuration still needs it.

## Considered Options

- Use the focused bounded contract above. Selected.
- Treat catalogue metadata, names or a preflight reference list as authoritative, risking changed semantics and deletion races.

## Decision Outcome

Apply the [complete accepted ADR-0123 contract](../../.agents/skills/inframeld-application-contracts/references/model-metadata-and-validation.md#accepted-metadata-and-reference-contract). It owns the exact behavior, bounds, current-state checks and failure outcomes. Use application-owned typed Known, Unknown and Conflict observations per supported model property. Keep three records distinct: advisory suggestions with exact provider/connection/model/role and source/version/time; reviewed effective settings owned by the Pipeline/profile/evaluator revision; and non-editable actual call observations. An explicit supported reviewed value wins over suggestions. Qualified selected-server observations may prefill ahead of pinned catalogue suggestions, but refresh only proposes a diff. No refresh rewrites saved settings, historical accounting or an existing profile.

The developer explicitly approved the presented batch-4 contracts and delegated selection of all remaining decisions to the assistant on 2026-10-29, requesting repository/GitHub recording and plain-language justification. This resolution is accepted under that authority. It selects logical policy, not implemented code or passing qualification.

## Consequences

Typed metadata and one reference gate add explicit checks, but prevent silent setting changes, leaked hidden dependencies and broken retained versions. Content-free audit history can remain after safe deletion.

Alice saves a 32k context limit even though a catalogue advertises 128k. Her value stays in force. Bob cannot delete the shared connection while an old retained PipelineVersion still references it, and removing its key is a separate deliberate action.

Implementation, measured support and qualification remain separate. A chosen threshold is not a measured result. No application code, public endpoint or passing runtime evidence is delivered here.

## Links

- [Owning contract](../../.agents/skills/inframeld-application-contracts/references/model-metadata-and-validation.md#accepted-metadata-and-reference-contract)
- [Decision finalization](../development/guides/architecture-decisions.md#just-in-time-architecture-decisions)
