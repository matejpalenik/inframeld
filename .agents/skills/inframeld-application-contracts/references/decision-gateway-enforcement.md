# PD-CONTRACTS-01: Enforce model policy on the actual outbound path

**Status:** PENDING

**Owner:** `inframeld-application-contracts`

**Issue kind:** Shared adapter contract and security qualification.

This reference supports a future discussion. Its recommendation is not accepted behavior. Current guides and ADRs retain authority.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Non-binding recommendation](#non-binding-recommendation)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Open questions and required evidence](#open-questions-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice approves a model hostname. It later resolves to private metadata infrastructure, or a library follows a redirect and retries a paid request after a timeout. Checking the saved URL once does not enforce what the socket sends or where it connects.

Destination, credential and retry policies are selected. The actual pinned adapter/transport mappings and assembled enforcement remain unfinished. Metadata reads, probes and nested Evaluation calls must not acquire a separate unguarded path.

## Accepted context and evidence

Every remote model request uses ModelGateway. Validate actual destinations, TLS, configured local HTTP exceptions and secret/destination binding. Do not inherit arbitrary proxy behavior, ambient credentials, redirects or library retries. Current connection revisions and supported settings remain explicit.

Provider waits stay outside SQL transactions. A timeout with uncertain dispatch does not authorize a new paid call. Preserving immutable model settings does not freeze a shared connection’s current access configuration. The concrete LiteLLM integration still needs pinning and qualification where documented.

## Alternatives and trade-offs

1. **Use a narrowly controlled embedded transport path.** Qualify supported adapter hooks and route every allowed request through one enforceable connection path. This keeps deployment simple, but unsupported bypasses must be rejected and hooks must genuinely control DNS/socket behavior.
2. **Combine adapter checks with supported host egress enforcement.** Constrain the actual process/network boundary as well as request mapping. This adds defense against library bypass, but requires deployment-specific configuration and tests. It is not permission for a separate gateway service.

## Non-binding recommendation

**Proposal only.** Prefer explicit supported adapter mapping plus real network-boundary enforcement where required by the accepted threat model. Qualify the assembled path using a private hostile test endpoint. Do not assume a library name or hostname allowlist proves enforcement.

## Decision trigger and stopping boundary

Before implementing model adapters/metadata/probe dispatch or selecting the actual transport/egress mechanism.

Pause unresolved enforcement interfaces. Production/security claims wait for assembled qualification, while authorized private tests of accepted requirements may proceed.

## Architectural impact and dependencies

Shared ModelGateway, connection/secret resolution, bootstrap networking and every domain model caller. Update model-dispatch and nested-call sequences without adding another business domain.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-05: Implement and qualify the selected provider-secret lifecycle](../../inframeld-access-models/references/decision-provider-secret-lifecycle.md). For secret lifecycle and deployment-key integration.
- [PD-CONTRACTS-02: Coordinate budget policy, reservations and uncertain settlement](decision-spending-coordination.md). For reservation/settlement at dispatch.

## Open questions and required evidence

- What actually controls DNS resolution, socket destination, redirects and proxies?
- Which adapters/settings are supported and which fail closed?
- How are usage, malformed outputs and unknown dispatch mapped?
- How do cancellation and late SDK results avoid success or hidden retry?
- What tests cover metadata, reranking, repair and private/local models?

## Sources and finalization

- [Destination policy](model-dispatch-and-destinations.md#destinations).
- [Dispatch and freshness](model-dispatch-and-destinations.md#dispatch).
- [Gateway decision](../../../../docs/adr/ADR-0023-route-every-model-request-through-modelgateway.md).

When the trigger applies, follow [the decision finalization workflow](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions). Obtain explicit approval of the concrete design and named documentation edits, reconcile affected sources and diagrams, and complete the repository-wide consistency pass before dependent implementation. Acceptance does not establish runtime qualification or authorize application writes.
