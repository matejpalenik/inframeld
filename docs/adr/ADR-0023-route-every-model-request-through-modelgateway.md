# ADR-0023: Route every model request through ModelGateway

Status: Accepted

**Date:** 2026-09-24

## Context and Problem Statement

Generation, embedding, and evaluation can otherwise create separate provider clients with inconsistent credentials, budgets, destination checks, retries, and error handling.

## Considered Options

- One application-owned ModelGateway boundary for every model request.
- Independent provider clients inside each feature or evaluation library.
- A required separate LiteLLM Proxy service.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Send every Inframeld remote model request through ModelGateway. Domain and application code use application-owned contracts; provider-specific adapters stay outside those rules. Support approved custom/private OpenAI-compatible connections and customer credentials in OSS. Local parsing and reranking retain their separate documented execution boundaries.

**Example.** An evaluation judge must use the same approved model boundary as an ordinary answer. Giving the evaluator its own API key would bypass the selected boundary.

## Consequences

- Provider access, credentials, safety checks, and retry decisions have one integration boundary.
- The application must qualify each provider capability and every nested evaluation-library call. API compatibility or a model alias is not proof of supported behavior, unchanged model meaning, or safe retries.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current model connections](../development/model-connections.md).
- [Current evaluation](../development/evaluation.md).
- Related decisions: [ADR-0024](ADR-0024-approve-outbound-destinations-before-model-calls.md), [ADR-0025](ADR-0025-separate-connection-meaning-from-replaceable-credentials.md).
