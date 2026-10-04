# ADR-0056: Support explicit local, hosted or disabled reranking

**Status:** Accepted; partially supersedes ADR-0042's local-only selection and unresolved local model choice.

**Date:** 2026-10-01. This records the previously accepted local/hosted/disabled reranking choices, with implementation ownership in the [delivery traceability index](../development/cli-delivery-plan.md#decision-coverage).

## Context and Problem Statement

Alice may generate answers with one provider, embed with another and rerank using a hosted provider such as Cohere or Voyage. A local option remains valuable for an easy first run without another API credential. ADR-0042's local-only wording conflicts with these accepted choices.

## Considered Options

- Retain only local reranking or explicit none.
- Support explicit local, hosted and disabled choices through the existing application boundaries.
- Infer a fallback from unavailable credentials or reranker failure.

## Decision Outcome

Select three explicit modes: `none`, `builtin` and `connection`. Built-in mode selects the Ettin 32M reranking bundle. Its exact artifact/tokenizer pins, license packaging, supported language/input behavior and CPU/memory/quality limits still require qualification. Selection is not proof of benchmark superiority or a promise of universal language support.

Hosted mode selects an authorized shared current connection and a supported reranking model. It uses ModelGateway and embedded LiteLLM, including destination checks, credentials, limits, budgets, cancellation and actual execution attribution. Hosted model setup reuses ordinary role/model/connection screens and optional preflight; it is not a separate credentials system.

Preserve ADR-0042's bounded application-owned Reranker contract: only supplied permitted candidates may be scored or reordered, with valid IDs and finite scores. Never silently switch mode, model or provider on failure. Local mode needs no remote credential, and disabled mode is deliberate configuration.

## Consequences

- Users can test different rerankers experimentally before explicitly saving and building their pipeline.
- The gateway adapter matrix must qualify each hosted operation; an OpenAI-compatible label does not imply reranking support.
- Deployment packaging includes pinned local assets rather than downloading models during requests. Local inference has no external model API charge but still consumes resources.
- No new reranking service or arbitrary local-model catalog is introduced.

## Links

- [ADR-0042](ADR-0042-rerank-selected-evidence-through-a-local-cross-encoder-boundary.md).
- [Pipelines: reranking](../development/pipelines-and-releases.md#reranking).
- [Model connections](../development/model-connections.md) and [CLI model-management journey](https://github.com/matejpalenik/inframeld/issues/167).
