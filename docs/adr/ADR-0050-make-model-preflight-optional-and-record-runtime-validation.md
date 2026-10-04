# ADR-0050: Make model preflight optional and record runtime validation

**Status:** Accepted. Partially supersedes [ADR-0025](ADR-0025-separate-connection-meaning-from-replaceable-credentials.md), specifically its prerequisite for a separate role probe before readiness. [ADR-0054](ADR-0054-use-shared-current-model-connections.md) subsequently replaces consumer-pinned connection meaning with shared current access configurations, preserving separate credentials and actual-revision validation evidence.

**Date:** 2026-09-28

## Context and Problem Statement

Alice already uses her company's model gateway. She wants to configure Inframeld and run a real workload without paying for another synthetic test first. Earlier onboarding required validation of the current credential revision before first publication, even when the configuration was complete and the real operation would enforce the same response checks.

A preflight is an extra, limited model request made to check access and compatibility before ordinary work. It can catch errors early, but consumes time, quota and potentially money. A successful preflight also cannot guarantee that the provider will remain available. Mandatory input, security and response validation solve a different problem and must not become optional.

## Considered Options

- Require synthetic role probes before first publication. This discovers many configuration failures early, but makes an extra provider call a prerequisite for real work.
- Allow setup to defer probes, but require them later before publication. This moves the interruption without removing the prerequisite.
- Recommend optional preflight, retain all runtime checks, and automatically record successful real model calls as role-specific validation evidence.

## Decision Outcome

Select optional preflight and automatic runtime validation evidence. A complete, authorized configuration may proceed to ordinary builds and queries without prior synthetic success. First publication does not require a validated-model marker. It still requires a complete ready PipelineVersion, verified materializations, usable required local dependencies and the normal authorization and publication guards.

A completed real model call marks only its actual connection access revision, credential revision, model, role and relevant configuration as validated, after all required response checks pass. A successful embedding call does not validate generation, and generation does not validate embeddings. Record whether evidence came from preflight or real use and when it occurred. An HTTP success alone, malformed output, an incomplete response or an uncertain outcome is not validation evidence.

Credential replacement makes the replacement untested without changing Pipeline meaning or requiring a new synthetic call. Old or late results cannot validate a different revision or revive a removed credential. Validation is evidence of past compatibility, not authorization, live health, answer-quality certification or permission to publish.

The [model-connections guide](../development/model-connections.md#roles) owns the runtime and failure rules. [Onboarding](../development/onboarding.md#models) owns the first-use path. [The data model](../development/data-model.md#model-validation-evidence) owns evidence identity and applicability.

## Consequences

- Users can skip extra paid requests and learn from real workloads. Optional preflight remains recommended because failure may otherwise be discovered after document processing or embedding costs have already occurred.
- Unknown embedding dimensions must still be obtained or explicitly configured before freezing an embedding profile. Real vectors must match that profile before index readiness can be published.
- All ModelGateway security, permission, credential, destination, response and retry checks remain mandatory. Missing secrets, malformed responses and unavailable dependencies remain explicit failures, never fallback triggers.
- UI and CLI status must distinguish untested configuration, recorded successful validation and later failures. They must not portray a saved key or a skipped check as success.
- No new provider service, certification framework or generic workflow engine is introduced. Exact persistence and wire schemas remain implementation work. Documentation acceptance does not establish runtime qualification.

## Links

- [ADR-0025](ADR-0025-separate-connection-meaning-from-replaceable-credentials.md): historical connection-pinning and probe rationale; [ADR-0054](ADR-0054-use-shared-current-model-connections.md) owns current connectivity and retains separate credentials.
- [ADR-0023](ADR-0023-route-every-model-request-through-modelgateway.md): universal model boundary.
- [ADR-0040](ADR-0040-bind-pipeline-versions-to-verified-profile-specific-materializations.md): unchanged index-readiness requirement.
- [Current model connections](../development/model-connections.md#roles), [onboarding](../development/onboarding.md#models) and [validation evidence](../development/data-model.md#model-validation-evidence).
- Implementation and integration-test qualification are pending.
