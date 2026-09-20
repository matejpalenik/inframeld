# ADR-0016: Docling processing and bounded reranking adapters

**Status:** Accepted — built-in adapters and their boundaries. Qualification of the pinned implementation remains pending. **Revised:** 19 September 2026. **Required approach:** Application-owned processing and reranking contracts, isolated document conversion, bounded local inference, and one model gateway for every LLM call. **Related:** [Parser isolation](ADR-0010-secure-document-ingestion-boundary.md), [profiles and materializations](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md), [model gateway](ADR-0006-byok-provider-boundary.md).

## Context

Inframeld prepares documents for search and then selects evidence to help answer questions. Two different stages contribute to that process.

**Document processing** reads a source file and divides its content into chunks: bounded excerpts with references back to their original locations. **Reranking** happens after retrieval. It takes the candidates already found for a question and scores or reorders them before they are used as evidence.

From first principles, these stages have different responsibilities. Processing defines the excerpts available to search; reranking changes the order of existing candidates. Neither should give an external library ownership of application identities, permissions, or stored data formats.

We need useful built-in implementations without turning v1 into a plugin platform. We also need predictable resource use: document conversion must remain isolated, and local reranking must not block request handling or exhaust the host’s memory.

## Decision

**Use Docling as the built-in document-processing adapter for PDF, Markdown, and plain text. Expose processing through `DocumentProcessor` and `Chunker`, and expose reranking through a separate `Reranker` port with a pinned local cross-encoder or the explicit `none` option.**

Keep all inputs and outputs application-owned, enforce processing isolation and resource limits, and make missing capabilities fail visibly. Preserve the existing internal hook and webhook contracts without implementing deferred extension or delivery systems.

OpenEvals and configurable Luna remain the evaluation choices in ADR-0008. Custom evaluators are deferred; this decision does not introduce another evaluation system.

### 1. Convert documents into application-owned artifacts and chunks

A **port** is an application-owned interface describing a capability. An **adapter** implements that interface using a particular library or runtime.

| Port | Responsibility |
| --- | --- |
| **`DocumentProcessor`** | Converts an admitted input into a canonical parsed artifact whose structure is defined by Inframeld. Admission means the application has accepted the input for processing. |
| **`Chunker`** | Produces bounded chunk candidates with source spans. A source span identifies where an excerpt came from in the original document. |

A **canonical parsed artifact** is the application’s standard representation of a parsed document. Downstream code uses that representation rather than needing to understand Docling’s internal objects.

The logical data flow is:

```text
Admitted source document
    -> DocumentProcessor
        -> Application-owned parsed artifact
            -> Chunker
                -> Bounded chunk candidates with source spans
```

Docling supplies the built-in adapter for PDF, Markdown, and text. Translate its native types at the adapter boundary: **Docling objects must not appear in domain or application contracts, and Docling’s own format must not be the only durable artifact schema.** A schema defines the structure of the stored data.

This keeps the processing result understandable to the application independently of the library that produced it.

### 2. Coordinate processing in the worker, but isolate conversion

The worker coordinates processing. It does **not** execute document conversion inside its privileged environment. Conversion runs in the offline, fresh-per-attempt sandbox defined by [ADR-0010](ADR-0010-secure-document-ingestion-boundary.md).

A **sandbox** is the restricted execution environment for one processing attempt. The parser-isolation ADR controls its enforcement; selecting Docling does not weaken that boundary.

Pin the Docling revision, model and tokenizer revisions, and every option that can affect output. A **tokenizer** divides text into the units used for token counting and model input. Changing it can therefore change chunk boundaries even when the source text is unchanged.

Include required assets in the approved runtime image, or provision them through controlled setup before jobs run. Never fetch assets from URLs supplied by a document.

**A configured `ModelGateway` connection does not give the parser network access.** Model-call configuration and parser permissions are separate boundaries.

### 3. Record processing choices in an immutable profile

A **processing profile** records how a source is turned into parsed content and chunks. It is immutable: changing the configuration creates a different profile rather than silently changing what an existing profile means.

The profile records supported formats, tokenizer and chunking behavior, processing limits, and parser/model identity. Supported bounded options include hybrid chunking, chunk-token limits, peer merging, and table-header behavior.

| Option | What it controls |
| --- | --- |
| **Hybrid chunking** | The supported chunking strategy that combines document structure with token-size constraints. |
| **Chunk-token limits** | How much text a chunk may contain, measured using the configured tokenizer. |
| **Peer merging** | Whether compatible peer chunks can be combined within the supported limits. |
| **Table-header behavior** | How table-header information is handled in processing and chunk output. |

These are supported configuration choices, not permission to install an arbitrary chunking implementation.

**Optical character recognition (OCR)** extracts text from images, such as scanned pages. It is usable only when the explicitly supported assets and processing limits exist. Supporting PDFs does not make every OCR configuration available automatically.

#### A profile change creates new processing results, not another upload requirement

A **processing generation** identifies the result produced from a source under a particular processing profile. Changing the profile creates a new generation. The unchanged source bytes do not need to be uploaded again.

For example, changing a chunk-token limit creates a new processing configuration and generation for the existing source. It must not rewrite the old generation’s meaning.

Start the user experience with a tested preset. The profile editor can expose more supported options later, but a simpler interface must not remove the underlying profile and generation identities.

### 4. Rerank only the candidates the application supplies

`Reranker` is separate from the processing ports. It receives a bounded query and candidate set, then returns scores or ordering for **those same candidate IDs**.

The supported choices are:

| Choice | Behavior |
| --- | --- |
| **Built-in local cross-encoder** | Uses the selected local model to assess query/candidate relevance and return scores or ordering. A cross-encoder considers the query and candidate together. |
| **Explicit `none`** | Skips reranking as a deliberate pipeline configuration choice. It is not an error-recovery substitute for a missing model. |

Select **one pinned built-in model initially**, rather than supporting arbitrary runtime model downloads. This ADR does not name the checkpoint to select. A **checkpoint** is the particular set of trained model weights used for inference.

Validate returned IDs, finite scores, configured bounds, timeout, and output shape. Finite scores exclude infinity and “not a number” values. Output validation must establish that the result still refers to the supplied evidence.

For example, if the input candidates are `C1`, `C2`, and `C3`, an ordering of `C3`, `C1`, `C2` refers to the original evidence. Introducing `C4` or replacing the text associated with `C1` violates the contract.

**Reranking cannot invent evidence, mutate source text, or expand access scope.** It changes the ordering or scores of authorized candidates, not their identity or content.

A reranker change is a pipeline-configuration change. It is not, by itself, a reason to re-embed the corpus—the selected body of documents. Embeddings are the numerical representations used for the earlier search step.

### 5. Bound local inference and preserve current permissions

Local inference still consumes CPU and memory. Run it through bounded execution and concurrency controls so synchronous model work neither blocks the API event loop nor exhausts host memory.

The **event loop** coordinates asynchronous request work. A long-running synchronous inference operation must not monopolize it. This ADR requires bounded execution without selecting a particular executor or inventing numerical limits before qualification.

Load required assets during controlled readiness checks, rather than downloading an arbitrary model when a request arrives. Readiness establishes whether the selected implementation is available for use.

**If the pipeline selects the cross-encoder and it is unavailable, fail visibly. Do not silently switch to `none`.** Otherwise the request would run a different configuration from the one the pipeline selected.

#### Authorize before sending candidate content

Retrieval authorizes candidates before sending them to a reranker or provider. Check current permission again where result release requires it.

The initial policy uses **group allowlists**, which identify groups permitted to access documents, and **fixed integration access**, under which an application uses its own assigned authority. Finer access-control lists (ACLs) remain deferred. Reranking must not create another permission policy or change the scope established by retrieval.

A future remote reranker must use an approved endpoint and declare its **data egress**: which content is sent outside the local environment and where it goes.

A future reranker that uses a large language model (**LLM**) must call the same `ModelGateway` as every other LLM operation. The required v1 **faithfulness judge**, which assesses whether an answer is supported by its evidence, follows that rule too. Local cross-encoder inference remains a separate `Reranker` implementation; the gateway rule does not make it a remote LLM call.

### 6. Keep the first-answer path simple without creating a second engine

The default path hides profile setup from the user. It does not bypass parser isolation or output validation.

For the **two-small-file timing scenario** in [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md), the recommendation is a conservative, prepackaged **text-first processing preset** with the existing explicit **`none` reranker**. Text-first means prioritizing documents whose text is already available rather than requiring OCR as part of the initial path.

OCR, cross-encoder downloads/loading, and judge setup are **not prerequisites for asking the first question**. This is a recommended preset for that scenario, not a measured timing guarantee or a removal of the richer built-in capabilities.

Broader supported processing and the built-in cross-encoder remain available through ordinary later configuration. The first-answer experience uses the same processing contracts and pipeline behavior; it does not introduce a special quickstart processing engine.

### 7. Preserve internal extension contracts without implementing a plugin platform

Keep the existing typed internal contracts:

| Contract | Responsibility and v1 scope |
| --- | --- |
| **`DocumentProcessor`** | Document conversion, with a built-in adapter. |
| **`Chunker`** | Bounded chunk production, with a built-in adapter. |
| **`Reranker`** | Candidate scoring/ordering, with the built-in cross-encoder and explicit `none` choices. |
| **`PipelineHook`** | A synchronous, blocking stage contract with explicit timeout, egress, and failure behavior. It is not a privileged arbitrary-code runtime. |
| **`WebhookDispatcher`** | An asynchronous notification contract. Subscriptions and delivery remain deferred. |

**Synchronous and blocking** means the pipeline waits for a hook’s stage outcome. Its timeout and failure rules must therefore be explicit. Keeping that contract does not authorize remote hook execution or user-supplied privileged code.

An **asynchronous webhook** notifies another system separately from the pipeline’s execution. It cannot control an in-flight pipeline. The in-app release workflow has no selected requirement for external callbacks, so the dispatcher interface does not imply a v1 delivery implementation or an external continuous-integration (CI) dependency.

Do not implement custom chunker registration, a plugin marketplace, arbitrary pipeline graphs, or remote hook execution. Custom evaluators also remain deferred under ADR-0008.

Internal interfaces may evolve when real requirements exist. Version public extension contracts when those features are selected, rather than inventing every future payload now. An internal interface is not a promise that a public extension system already exists.

### 8. Record the exact components and their licenses

Release evidence must identify the exact library, model, checkpoint, and sandbox-helper revisions, together with their license notices. Sandbox helpers are the tools used to enforce the processing isolation.

**Inframeld’s Apache-2.0 license does not relicense model weights, OCR engines, parser dependencies, or external sandbox tools.** Record the relevant notices for those components separately.

Do not select a model checkpoint based only on the license of the library that loads it. The loader and the trained weights are different release components.

The exact pinned implementation remains to be qualified. No new dependency was installed as part of this documentation change.

### 9. Verify the pinned implementation before making release claims

The following are acceptance requirements, not completed test results.

| Area | Required verification |
| --- | --- |
| **Source evidence** | Verify source-span correctness and deterministic identities for fixed processing inputs. |
| **Profile changes** | Verify that changed processing profiles produce new generations without requiring unchanged sources to be uploaded again. |
| **Parser isolation and output** | Deny external fetches, reject invalid parser output, and verify the whole pinned image under ADR-0010. |
| **Local resource use** | Exercise bounded reranking execution, concurrency, timeout, and memory behavior without blocking the API event loop. |
| **Reranker contract** | Reject changed or forged candidate IDs, invalid output shapes, non-finite scores, and outputs outside the configured bounds. |
| **Missing assets and failure** | Exercise unavailable parser/reranker assets and prove that a selected cross-encoder never silently becomes `none`. |
| **Permissions and model-call boundaries** | Verify authorization before candidate content reaches the reranker/provider and the required current checks before result release. The v1 judge must use `ModelGateway`. |
| **Observable reranker effect** | Use a fixture evaluation—a repeatable evaluation with defined inputs—to expose the effect of enabling the selected reranker. |
| **Default path** | Exercise the text-first, `none`-reranker scenario without requiring OCR, cross-encoder setup, or a judge, while preserving isolation and output validation. |

The fixture must show what enabling the reranker changes; this ADR does not assume it improves every case or assign an untested quality threshold.

**Qualify the complete pinned image under ADR-0010 before making security or performance claims.** Selecting a library or model is not evidence that the assembled implementation satisfies its boundaries.

## Consequences

### Positive

- **Application contracts remain independent of Docling and the reranking model.** Parsed artifacts, chunk candidates, source identities, and scores use application-owned representations rather than exposing library objects throughout the product.
- **Processing and retrieval changes remain distinguishable.** A processing-profile change creates new processing evidence without another source upload; a reranker change affects pipeline configuration without requiring new embeddings solely for that change.
- **First use stays small without weakening the normal path.** A tested text-first preset and explicit `none` choice avoid unnecessary setup while retaining isolation, validation, and access to richer built-in configuration later.

### Negative

- **The adapters still require implementation and release work.** Type translation, source-span validation, exact version/asset pins, license notices, and whole-image qualification remain Inframeld responsibilities.
- **Local processing and reranking consume bounded host resources.** Assets must be prepared and loaded deliberately, concurrency must be controlled, and unavailable selected capabilities cause visible failures rather than hidden substitutions.
- **Extensibility is intentionally limited in v1.** Internal contracts do not provide arbitrary model downloads, custom chunker registration, remote hooks, webhook delivery, a plugin marketplace, or custom evaluators.

## Alternatives considered

No separate comparative evaluation is recorded. The following approaches are excluded or deferred by this decision.

### Use Docling’s native objects as application contracts and the only stored format

**Ruled out.** The adapter translates into application-owned parsed artifacts and chunk candidates. Docling’s native types stay out of domain/application contracts, and its format cannot be the only durable artifact schema.

### Run conversion in the privileged worker or fetch assets during document processing

**Ruled out.** The worker coordinates conversion, but ADR-0010’s offline per-attempt sandbox executes it. Assets are supplied through the approved runtime or controlled setup, not document-supplied URLs. Model-gateway configuration does not grant network access to the parser.

### Silently skip a selected reranker when it is unavailable

**Ruled out.** `none` is an explicit configuration choice, not a fallback. A pipeline that selects the cross-encoder must fail visibly when that implementation cannot run.

### Support arbitrary model downloads and user-defined processing extensions immediately

**Deferred.** Start with one pinned built-in cross-encoder and supported processing profiles. Arbitrary runtime downloads, custom chunker registration, plugin marketplaces, arbitrary pipeline graphs, remote hook execution, and custom evaluators are not v1 implementation requirements.

### Implement webhooks because a dispatcher interface already exists

**Not required.** The current in-app release workflow does not depend on external callbacks or an external CI system. Preserve the internal contract, but defer webhook subscriptions and delivery. An asynchronous notification cannot take control of a running pipeline.

## References

| Reference | Responsibility |
| --- | --- |
| [ADR-0010: Parser isolation](ADR-0010-secure-document-ingestion-boundary.md) | Offline per-attempt conversion, enforced sandbox restrictions, output validation, and whole-image security qualification. |
| [ADR-0015: Profiles and materializations](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md) | Immutable processing profiles/generations and their relationship to indexed data and pipeline bindings. |
| [ADR-0006: Model gateway](ADR-0006-byok-provider-boundary.md) | The shared boundary for every LLM operation, approved endpoints, and declared data egress. |
| [ADR-0008: Evaluation](ADR-0008-deterministic-evaluation-and-release-decisions.md) | OpenEvals, the configurable Luna faithfulness judge, and deferred custom evaluators. |
| [ADR-0019: Default onboarding](ADR-0019-default-onboarding-and-first-publication.md) | The first-answer path and the two-small-file timing scenario using ordinary product behavior. |
