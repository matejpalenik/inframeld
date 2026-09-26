# ADR-0024: Approve outbound destinations before model calls

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Custom model endpoints are required, including private endpoints. Arbitrary request URLs could send credentials or protected evidence to unintended destinations.

## Considered Options

- Operator-approved connections with destination, DNS, TLS, and capability checks.
- Allow a caller to supply an arbitrary model URL.
- Prohibit all private/custom endpoints.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Send model traffic only through approved connections and the documented destination checks. Validate the configured origin and actual destination, preserve TLS/custom-CA controls, and bound capabilities. The operator-approved local Ollama HTTP exception is credential-free; a connection that needs an authentication secret must use certificate-verified HTTPS. A per-request URL is not a connection. Changing endpoint meaning requires deliberate connection handling and fresh credential provision, not forwarding an old secret automatically.

**Example.** Changing a connection from one origin to another must not silently send the first provider’s saved key to the second origin.

## Consequences

- OSS can support private/custom providers while keeping outbound authority explicit.
- Network behavior, DNS changes, redirects, authentication, and supported capabilities need qualification. An OpenAI-compatible label alone does not prove a destination is safe or supports the required operation.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current model connections](../development/model-connections.md).
- [Current deployment](../development/deployment.md).
- Related decisions: [ADR-0023](ADR-0023-route-every-model-request-through-modelgateway.md), [ADR-0025](ADR-0025-separate-connection-meaning-from-replaceable-credentials.md).
