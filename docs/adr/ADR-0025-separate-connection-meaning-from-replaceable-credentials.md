# ADR-0025: Separate connection meaning from replaceable credentials

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Saved pipeline and embedding configurations need a stable interpretation. Rotating an access secret should not force a new numerical meaning, but changing the endpoint or model configuration can.

## Considered Options

- Immutable semantic connection revisions with separate credential lifecycle.
- Treat every credential rotation as a new model meaning.
- Mutate an existing connection’s meaning while retained versions continue referencing it.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Freeze the connection/model meaning used by retained profiles and versions. Keep credential-only changes separate, with the accepted probe invalidation and replacement rules. Validate embedding and generation roles independently, even when they share one connection and key. A model alias does not prove an external provider’s implementation is unchanged.

**Example.** Replacing a revoked key preserves the selected endpoint and model revision, but requires the applicable role probe again before readiness is claimed.

## Consequences

- Credentials can be replaced without rewriting historical semantic configuration.
- The application must distinguish changes of access from changes of meaning and preserve the approved-destination boundary. A saved replacement key is not evidence that a role works.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current model connections](../development/model-connections.md).
- [Current data model](../development/data-model.md).
- Related decisions: [ADR-0023](ADR-0023-route-every-model-request-through-modelgateway.md), [ADR-0024](ADR-0024-approve-outbound-destinations-before-model-calls.md).
