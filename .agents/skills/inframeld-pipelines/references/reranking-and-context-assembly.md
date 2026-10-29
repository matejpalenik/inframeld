# Rerank evidence and fit the final context

<a id="rerank-evidence-and-fit-the-final-context"></a>

Alice retrieves twenty passages but allows at most five in the answer context. A reranker may reorder those same permitted passages. The context builder then fits whole passages in order without inventing evidence or silently changing model settings.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="rerank-bounded-evidence"></a>

<a id="reranking"></a>

<a id="6-rerank-bounded-evidence"></a>

## Rerank bounded evidence

The application-owned `Reranker` receives a size-limited question and candidate set and scores or reorders those same candidate IDs. It is separate from document-processing interfaces.

The supported choices are:

| Choice | Behavior |
| --- | --- |
| **Built-in local cross-encoder** | Uses the selected Ettin 32M bundle to assess query/candidate relevance and return scores or ordering. A cross-encoder considers the query and candidate together. Exact assets and runtime limits still need qualification. |
| **Hosted connection** | Uses an explicitly selected supported reranking model through ModelGateway and embedded LiteLLM, with ordinary current connection, credential, egress and budget checks. |
| **Explicit `none`** | Skips reranking as a deliberate pipeline configuration choice. It is not an error-recovery substitute for a missing model. |

Use one pinned Ettin 32M bundle rather than download arbitrary models during requests. [ADR-0056](../../../../docs/adr/ADR-0056-support-explicit-local-hosted-or-disabled-reranking.md) records the accepted local/hosted/none choices. Exact checkpoint/tokenizer pins, packaging/license notices, supported language/input behavior and resource/quality measurements remain qualification work. Mode is explicit. Unsupported hosted reranking fails without fallback.

Validate the output structure, IDs, configured limits, and timeout. Scores must be finite, excluding infinity and “not a number.” Every returned result must still refer to the supplied evidence.

For example, if the input candidates are `C1`, `C2`, and `C3`, an ordering of `C3`, `C1`, `C2` refers to the original evidence. Introducing `C4` or replacing the text associated with `C1` violates the contract.

**Reranking cannot invent evidence, mutate source text, or expand access scope.** It changes the ordering or scores of authorized candidates, not their identity or content.

Changing the reranker changes Pipeline configuration, but does not by itself require new corpus embeddings. Embeddings are the numerical values used by the earlier search step.

<a id="bound-local-inference-and-preserve-current-permissions"></a>

### Bound local inference and preserve current permissions

Local reranking still uses CPU and memory. Limit simultaneous work and run synchronous model computation without blocking the API's event loop or exhausting host memory.

The **event loop** coordinates asynchronous requests. One long model calculation must not monopolize it. The executor and numerical limits still need selection and testing.

Prepare and check required assets before marking the reranker available. Do not download arbitrary models when requests arrive.

**If the pipeline selects the cross-encoder and it is unavailable, fail visibly. Do not silently switch to `none`.** Otherwise the request would run a different configuration from the one the pipeline selected.

<a id="authorize-before-sending-candidate-content"></a>

### Authorize before sending candidate content

Check permission before giving excerpts to the reranker or provider, and recheck when returning protected results requires it.

The initial Access model uses document-group allowlists and applications' own current permissions. Finer access-control lists remain deferred. Reranking reuses retrieval's permitted selection instead of defining another access policy.

Hosted reranking is accepted for v1 and needs an approved endpoint and an explicit account of which permitted candidate text leaves the installation. It uses ModelGateway, as does an explicitly selected evaluation judge. Evaluation remains optional. No judge is required for first setup. The local cross-encoder remains a separate bounded Reranker implementation, not a remote language-model call.

<a id="generation-context-contract"></a>

<a id="fit-final-context-without-silently-changing-evidence"></a>

### Fit final context without silently changing evidence

Keep each retained passage's exact source-version/canonical-artifact identity and ordered segment mappings under accepted [PD-INDEXING-03](../../inframeld-indexing/references/decision-source-coordinates.md#approved-resolution). Reranking preserves those mappings while reordering candidates. Attribute final-context coverage only to actual retained text. Discontiguous excerpts cannot claim their missing middle, and generated labels have no invented source spans. This does not change the whole-passage fitting rule below.

The Pipeline has two separate limits: retrieve up to **20 candidate passages** initially, then include **at most 5 passages** in generation context. Both are configurable positive integers. The context limit cannot exceed the candidate limit. Apply both limits with or without reranking. Actual returned counts may be smaller.

Reserve the model's fixed input and saved effective `max_output_tokens`, using qualified model/token metadata. Append whole passages in ranked order until the next passage would exceed the remaining input allowance, then stop. Do not truncate, summarize, skip ahead, switch models or silently reduce output to make it fit. Distinguish oversized fixed inputs/first passage from ordinary no-evidence outcomes. Generation has a small supported configuration, including optional model-aware temperature, not arbitrary provider parameters. Exact ranges, presets and billing/reasoning semantics remain contract/adapter qualification.

For example, Alice retrieves up to 20 permitted passages, reranks that pool and permits at most 5 passages in generation. If only ranks 1-3 fit, rank 4 and everything after it are excluded, even when rank 5 is smaller. With reranking disabled, retain retrieval order and the same context cap. Do not send all 20 passages. These are counts of retrieved chunks, not documents or Evaluation's expected source passages.

The retrieval cap applies across the selected corpus after merging comparable, authorized results and deduplicating record identities, not independently per collection. It is not a physical shard-read limit. Establish permitted search scope before retrieval and retain bounded fanout/deadlines. Unrestricted global top-k followed by filtering is not equivalent. Fewer authorized results are normal. Missing required shards, exceeded safety bounds or a failed enabled reranker are failures, not ordinary short results. Never widen access or duplicate evidence to fill a cap.

Validate positive integer counts and `max_passages <= top_k` without silently adjusting them. Resource ceilings remain applicable. Changing a future setup preset does not rewrite existing saved values. These settings belong to working history and captured direct-query/evaluation/build inputs. Saving or importing them neither prepares data nor executes or publishes.

Fit against the qualified separate input, output and combined-window rules of the selected model. Reserve the complete fixed prompt, question, message/citation formatting and configured maximum output, including applicable reasoning categories. Do not use average answer length or assume separately tokenized strings sum exactly. Validate the final model-facing payload after observable adapter transformations. Source spans must describe the actual supplied text. Recheck cancellation, current access, shared connectivity and spending before dispatch.

| Condition | Required outcome |
| --- | --- |
| Fixed input and output reserve cannot fit | Configuration/context-size error before generation, with explicit input/configuration repair guidance |
| Evidence exists but rank 1 cannot fit | Context-size error. No empty-context answer or lower-ranked substitution |
| Nonempty prefix fits | Generate from that complete prefix. Authorized diagnostics show the cutoff |
| No permitted evidence was retrieved | Ordinary no-evidence behavior, not a fabricated token-fit failure |
| Unknown model/tokenizer limit semantics | Unsupported contract error until qualified metadata/counting is configured. No unrelated tokenizer treated as exact |
| Provider rejects size despite local validation | Visible execution failure. No silent shrink-and-retry or model switch |

Earlier query embedding or reranking can already have incurred cost when generation fitting fails. Spending failure does not authorize dropping evidence or shrinking output to make a call affordable. Generation fitting does not silently rechunk or rebuild data, and reranker-specific truncation rules do not authorize truncating generation evidence. Evaluation judges only final supplied context. Under recording/access policy, diagnostics distinguish configured limits from actual retrieved, submitted-to-reranker, returned-ranked and final-context counts. Never claim to have captured a full ranking when the provider returned only a subset.

<a id="generation-parameters"></a>

<a id="preserve-an-explicit-output-allowance-and-optional-temperature"></a>

### Preserve an explicit output allowance and optional temperature

Alice changes the generation model while retaining her saved temperature and output allowance. If the new model cannot honor them, identify the incompatible fields before saving. She must deliberately revise them. Neither a library's parameter-dropping option nor a provider error authorizes silently changing the requested behavior.

Every effective saved generation configuration has an explicit positive integer `max_output_tokens`. Guided setup proposes a qualified model-appropriate value for review. Export preserves the saved value and import does not replace it with the destination's current preset. A sample value such as 4096 is not a universal default. Missing input without a documented valid resolution fails rather than permitting an unlimited call.

This is an enforceable generation allowance, not a visible answer-length promise. Its provider mapping includes applicable generated-token categories, including reasoning where counted within the allowance. Different provider semantics need an explicitly qualified mapping, not just a renamed parameter. An unsupported mapping blocks dispatch. Budget admission separately bounds all applicable billable usage. This field alone is not a cost calculation. Provider output-limit exhaustion does not authorize an automatic continuation or another paid request.

Leave temperature unset unless deliberately selected. Unset means **Provider default**, not zero or an invented numeric default. Validate explicit temperature against the exact model/provider/protocol and preserve unset versus explicit values through save/export/import. Do not invent TOML nulls or an undocumented sentinel. Owns the portable representation. Partial edits retain unchanged settings. Complete file replacement reviews any resets. Provider defaults can change externally, and even supported temperature zero does not guarantee reproducibility.

Pipelines owns the selected connection ID, separate model identifier, prompt and supported generation parameters. The connection owns access configuration and separate credentials. Files cannot introduce keys, endpoint overrides, extra headers, retry controls, parameter-dropping switches or an unrestricted provider-options dictionary. Validate known constraints before save and current applicable constraints again at dispatch. Static validation makes no model request and proves no provider health. Synthetic tests remain optional. A provider rejection is a failure, not permission to remove parameters and retry.

ModelGateway infrastructure maps application-owned settings into qualified provider inputs. Pipeline edits do not change shared connection settings or publish a Deployment, and evaluation generator/judge choices remain separate. Human editing, TOML and noninteractive inputs share these rules. Errors identify invalid fields without leaking credentials or unnecessary prompt content.

Qualification must cover exact-fit/one-token-over boundaries, oversized first passages, deliberate lower-rank exclusion, disabled reranking, non-ASCII input, reasoning/output mappings, private/unknown models, provider size rejection, forbidden raw parameters, unset/explicit round trips, incompatible model changes, current-access loss, cancellation and uncertain paid calls. Numerical presets, supported ceilings, precise schemas and response/finish-reason fields remain engineering deliverables, not runtime evidence supplied by this guide.

Use `query --deployment <name>` for live execution and `query --pipeline <name>` to query saved working settings directly. The earlier `--preview` flag is no longer needed. This syntax change does not change Pipeline Query permissions or the requirement to capture fixed working-configuration inputs. See [delivery ownership](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md).

<a id="offer-reranking-without-adding-mandatory-work"></a>

### Offer reranking without adding mandatory work

Use a qualified text-first Docling hybrid processing preset with explicit limits. Offer reranking through the shared model-role screens: recommend the qualified built-in Ettin 32M option for English workloads, preserve explicit `none`, and allow a supported hosted connection/model. A highlighted recommendation does not silently save or run it. Text-first processing handles existing text without requiring OCR to read scanned pages.

Do not quietly add model/profile downloads, a local generation model, OCR, reranking or a judge. Built-in reranking runs on the selected backend using packaged assets, not in the CLI. Hosted selection reuses connection/credential screens and optional testing, with cost review before any model call. A different embedding model requires a new profile and materialization, not relabelling old vectors.
