# PD-CONTRACTS-01: Enforce model policy on the actual outbound path

**Status:** ACCEPTED on 2026-10-29 in [ADR-0104](../../../../docs/adr/ADR-0104-enforce-one-qualified-outbound-model-path.md). Implementation and qualification remain pending.

**Owner:** `inframeld-application-contracts`

**Issue kind:** Shared adapter contract and security qualification.

The developer explicitly approved all three model-calls, provider-secrets and spending proposals on 2026-10-29 and requested their repository and GitHub documentation. Acceptance selects the contract, not implemented adapters or passing qualification.

## Contents

- [Problem and example](#problem-and-example)
- [Accepted context and evidence](#accepted-context-and-evidence)
- [Alternatives and trade-offs](#alternatives-and-trade-offs)
- [Approved resolution](#approved-resolution)
- [Decision trigger and stopping boundary](#decision-trigger-and-stopping-boundary)
- [Architectural impact and dependencies](#architectural-impact-and-dependencies)
- [Implementation and required evidence](#implementation-and-required-evidence)
- [Sources and finalization](#sources-and-finalization)

## Problem and example

Alice approves a model hostname. It later resolves to private metadata infrastructure, or a library follows a redirect and retries a paid request after a timeout. Checking the saved URL once does not enforce what the socket sends or where it connects.

Destination, credential and retry policies are selected. The actual pinned adapter/transport mappings and assembled enforcement remain unfinished. Metadata reads, probes and nested Evaluation calls must not acquire a separate unguarded path.

## Accepted context and evidence

Every remote model request uses ModelGateway. Validate actual destinations, TLS, configured local HTTP exceptions and secret/destination binding. Do not inherit arbitrary proxy behavior, ambient credentials, redirects or library retries. Current connection revisions and supported settings remain explicit.

Provider waits stay outside SQL transactions. A timeout with uncertain dispatch does not authorize a new paid call. Preserving immutable model settings does not freeze a shared connection’s current access configuration. The concrete LiteLLM integration still needs pinning and qualification where documented.

## Alternatives and trade-offs

These preserve the options considered before approval. The approved resolution below owns the selected contract.

1. **Use a narrowly controlled embedded transport path.** Qualify supported adapter hooks and route every allowed request through one enforceable connection path. This keeps deployment simple, but unsupported bypasses must be rejected and hooks must genuinely control DNS/socket behavior.
2. **Combine adapter checks with supported host egress enforcement.** Constrain the actual process/network boundary as well as request mapping. This adds defense against library bypass, but requires deployment-specific configuration and tests. It is not permission for a separate gateway service.

## Approved resolution

Every model operation, role, optional probe, metadata read, reranker and nested Evaluation/Ragas call must use the approved gateway path. Support only explicitly mapped and qualified pinned adapter features. Unsupported provider/settings or a transport bypass fails before dispatch, without silently dropping settings.

Use a controlled embedded transport together with the supported host/network egress policy. Validate scheme, normalized host/port/base path and resolved IPv4/ IPv6 destinations at connection time. Connect through the validated route and retain correct hostname/certificate verification. A hostname check followed by an independent uncontrolled resolution is insufficient. Connection reuse remains bound to the approved origin and route.

Disable automatic redirects for the supported initial profile. Require the configured connection to name the final endpoint. Do not inherit ambient proxy configuration, credentials, router fallbacks or independent library/provider-SDK retries. Explicitly qualified deployment egress configuration is distinct from an arbitrary caller-supplied proxy. Reject adapters that cannot enforce the path.

Preserve verified HTTPS and customer-CA support. Private networks require explicit deployment allowlisting. Always reject link-local/cloud-metadata destinations. Preserve only the already approved credential-free local Ollama HTTP exception, with no saved provider key or authentication secret attached. Do not add another gateway service or a new public network proxy.

Before each bounded call, check current principal authority, connection access revision and model compatibility, the current credential, spending reservation and cancellation/ownership. Access-revision changes stop remaining dispatches in the admitted operation rather than changing its inputs. Credential-only rotation resolves the current secret without silently changing endpoint/model selection. Provider waits stay outside SQL transactions.

Map the observed call into a known not-sent outcome, a known response/result or failure, or dispatch uncertainty. A malformed result is not success. Absence of trustworthy usage is not zero billing. A timeout/cancellation after a possible send never triggers automatic redispatch. Late observations retain operation and call attribution, cannot bypass lost worker ownership or current disclosure, and cannot create a second settlement. Accepted safe-repeat protocols remain separate from uncertain paid model requests.

Metadata reads are bounded, typed and tied to the selected connection/model. Keep provenance and supported known/unknown observations, not arbitrary provider dictionaries. Optional validation is not an implicit synthetic paid call. Existing metadata/connection specification work in #121 must still cover its full scope, so this transport decision alone does not automatically resolve every #121 choice.

## Decision trigger and stopping boundary

Apply this accepted contract when the implementation reaches its original trigger. Concrete method names and physical representations remain ordinary implementation choices. Qualification limits support and release claims, not authorized evidence gathering. Discuss a new policy choice only if it would change this approved contract.

## Architectural impact and dependencies

Shared ModelGateway, connection/secret resolution, bootstrap networking and every domain model caller. Update model-dispatch and nested-call sequences without adding another business domain.

Load neighboring decisions only under these conditions:

- [PD-ACCESS-05: Implement and qualify the selected provider-secret lifecycle](../../inframeld-access-models/references/decision-provider-secret-lifecycle.md). For secret lifecycle and deployment-key integration.
- [PD-CONTRACTS-02: Coordinate budget policy, reservations and uncertain settlement](decision-spending-coordination.md). For reservation/settlement at dispatch.

## Implementation and required evidence

These are required cases and evidence, not recorded passing tests.

Hostile private endpoints must test DNS changes, forbidden IPv4/IPv6 routes, redirects, invalid/custom-CA TLS, inherited proxy/credential settings, nested calls, SDK retries/fallbacks, malformed results, timeouts, cancellation and late results. Demonstrate current-credential rotation/removal and connection revision changes. Unqualified combinations cannot be advertised as supported.

## Sources and finalization

- [Destination policy](model-dispatch-and-destinations.md#destinations).
- [Dispatch and freshness](model-dispatch-and-destinations.md#dispatch).
- [Gateway decision](../../../../docs/adr/ADR-0023-route-every-model-request-through-modelgateway.md).

[ADR-0104](../../../../docs/adr/ADR-0104-enforce-one-qualified-outbound-model-path.md) records the approval and rationale. Follow [decision finalization](../../../../docs/development/guides/architecture-decisions.md#just-in-time-architecture-decisions) for a later policy change. This documentation approval does not authorize application implementation or claim successful qualification.
