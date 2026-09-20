# ADR-0006: OSS model gateway, BYOK, and custom endpoints

**Status:** Accepted — gateway boundary, OSS scope, persistent application-entered provider credentials, and PostgreSQL/PyNaCl credential storage. Implementation tests remain necessary. **Revised:** 19 September 2026. **Required approach:** One application-owned gateway for every LLM call; custom endpoints and customer-supplied credentials available in OSS. **Related:** [Lineage](ADR-0003-immutable-rag-lineage-and-release-identities.md), [evaluation](ADR-0008-deterministic-evaluation-and-release-decisions.md), [ingestion](ADR-0010-secure-document-ingestion-boundary.md).

## Context

Inframeld needs models for several tasks. A **generation model** produces an answer from instructions and retrieved evidence. An **embedding model** converts text into numerical vectors used for similarity search. Evaluation also uses a **faithfulness judge**: a model that checks whether an answer is supported by its supplied evidence.

These tasks may use a public provider, a local model, or a customer's private model gateway. **BYOK**, or _bring your own key_, means the customer supplies the credentials needed to use their provider rather than depending on a provider account funded by Inframeld.

From first principles, each model call needs a defined operation, an approved destination, and the appropriate credentials. Those responsibilities remain the same whether the call generates a customer answer, embeds a document, or judges an evaluation result. Letting each feature configure its own provider client would make it possible to bypass the shared endpoint, credential, and retry rules.

The product must also distinguish **what a connection means** from **which credential currently permits its use**. Rotating a key should not rewrite a pipeline's history, while changing its model or destination must not silently change an old pipeline's behavior.

## Decision

**All generation and embedding calls use the application's typed `ModelGateway` interface. The initial adapter uses the embedded LiteLLM Python SDK. Customers can configure approved public, private, and local endpoints in the Apache-2.0 open-source product and save their provider credentials through the application API.**

Connection revisions preserve model configuration. Credentials can be replaced separately. Endpoint restrictions, response validation, and centrally owned retry rules apply to every caller, including evaluation libraries.

### 1. Route every LLM call through the same application boundary

A **port** is an application-owned interface describing a capability the application needs. An **adapter** implements that interface using a particular library or service.

`ModelGateway` is the typed port for chat/generation and embeddings. Its requests and results have defined application types rather than requiring business modules to work directly with provider clients.

| Operation | Required path |
| --- | --- |
| **Generate an answer to a user query** | Generation through `ModelGateway`. |
| **Embed a query for search** | Embeddings through `ModelGateway`. |
| **Embed document chunks while building an index** | Embeddings through `ModelGateway`. A chunk is a document excerpt prepared for retrieval. |
| **Generate answers during an evaluation** | Generation through `ModelGateway`. |
| **Run the v1 faithfulness judge** | A model call through `ModelGateway`, even when an evaluation library coordinates it. |
| **Classify content using an LLM** | The same gateway rule applies whenever classification uses a large language model (LLM). |

The initial path is:

```text
Query, indexing, or evaluation use case
    -> ModelGateway: application-owned interface
        -> Embedded LiteLLM Python adapter
            -> Configured OpenAI, Ollama, or approved compatible endpoint
```

**One gateway boundary does not mean one model or one endpoint.** Different roles can select different configured connections while using the same application interface.

The initial adapter supports configured OpenAI and Ollama connections, plus deployment-approved **OpenAI-compatible endpoints**: endpoints that implement the relevant OpenAI-style API operations. A customer's enterprise gateway is another endpoint behind this adapter, not a separate application path.

LiteLLM runs as an embedded Python software development kit (SDK). **No separate LiteLLM Proxy service is required.** Alternative adapters may implement `ModelGateway`, but application modules cannot bypass the port.

A third-party evaluation library must not create an independent provider client. Its model calls use the same gateway as the rest of Inframeld.

### 2. Keep custom model access in OSS and local processing separate

The **open-source software (OSS)** product includes custom endpoints, customer LLMs, private-network endpoints, custom certificate-authority trust, BYOK, and the core pipeline release loop.

These capabilities must work under Apache-2.0 without code from `/ee`, a licensing server, or a platform-funded provider account. Future **Enterprise Edition (EE)** routing policies or organization administration must not remove them from the core product.

#### Not every model-related component is a remote LLM call

The local cross-encoder reranker uses a separate `Reranker` port. A **reranker** reorders retrieved candidates according to their relevance; the selected cross-encoder performs that work locally.

Docling uses the `DocumentProcessor` and `Chunker` ports to process documents and divide them into retrieval chunks.

Neither component secretly makes remote LLM calls. Any future remote processing must separately declare its **data egress**: what data leaves the configured environment and where it goes.

### 3. Preserve connection meaning while allowing credential rotation

A **connection** is a project-owned configuration for reaching a model endpoint. It has a stable identity and immutable **semantic configuration revisions**: versions of the configuration that determine which model behavior is being requested.

Pipeline and profile records reference the selected revision. Serving must not look up a mutable “current endpoint” that can silently redirect an existing pipeline.

Credentials are separate, replaceable capabilities associated with the connection. They authorize a call; they are not the model's semantic identity.

An endpoint's **origin** is its scheme, hostname, and port. Its base path identifies the API path beneath that origin.

| Change | Required behavior |
| --- | --- |
| **Rotate a credential without changing model semantics** | Preserve connection and pipeline lineage. The replacement credential does not inherit the old role-validation status. |
| **Change embedding semantics** | Create a new embedding profile and materialization rather than change the meaning of existing vectors. A materialization is the prepared searchable index for the selected inputs and profiles. |
| **Change the chat model, prompt, or retrieval configuration** | Create a new pipeline version. |
| **Change the endpoint origin** | Create a new connection and require explicit credential entry. Never forward an existing key to the new origin implicitly. |

An **embedding profile** records the model identity or alias, connection revision, dimensions, normalization, and distance metric. Dimensions specify how many numerical values each embedding contains; normalization and the metric define how those vectors are prepared and compared.

#### A recorded alias is not proof of an unchanged external model

Record the resolved model revision when the provider exposes it, and pin model revisions where supported.

A gateway alias can change outside Inframeld. Recording the alias identifies what was configured, but it cannot prove that the underlying model never changed. Make that remaining reproducibility limitation visible rather than treating the alias as a guaranteed fixed implementation.

### 4. Approve endpoint destinations before allowing model calls

Supporting customer endpoints creates an **SSRF**, or _server-side request forgery_, boundary. The application must not let an ordinary caller turn a model request into an arbitrary outbound request from the server.

There are two distinct configuration responsibilities:

| Who | What they may configure |
| --- | --- |
| **Deployment administrator** | Approves the allowed endpoint origins through deployment configuration. |
| **Authorized project owner** | Creates a connection within that deployment policy. A project connection cannot expand it. |

A query or evaluation selects configured model access; **it cannot supply its own endpoint URL**.

This allows private Enterprise or other customer endpoints without granting ordinary users arbitrary network access.

#### Validate both the configured URL and the actual destination

| Boundary | Required behavior |
| --- | --- |
| **URL structure** | Validate the scheme, hostname, port, and normalized base path. Also validate the actual destination, not just the displayed URL. |
| **Remote transport** | Require TLS certificate verification. TLS protects the connection and verifies the endpoint's certificate. Mount a customer certificate authority (CA) when its private service requires custom trust; do not disable verification. |
| **Local HTTP exception** | Explicitly operator-approved local Ollama over HTTP is a narrow exception. It is not permission to use unverified remote endpoints. |
| **Credentials in URLs** | Reject URL user-info, such as an embedded username/password, and credential-bearing query strings. |
| **Redirects** | Reject redirects to a different origin. |
| **Forbidden destinations** | Reject link-local and cloud-metadata addresses. These are not made acceptable merely by supporting private endpoints. |
| **Private networks** | Permit private address ranges only through explicit deployment allowlisting. A blanket ban on private addresses would prevent the approved customer-gateway use case. |
| **Caller-controlled proxies** | Do not accept arbitrary proxy settings from API callers. |
| **DNS and network routing** | Revalidate destinations resolved through the Domain Name System (DNS), and enforce the permitted route through host/network egress restrictions. |

**A one-time hostname string check is insufficient.** A hostname can resolve to a different destination later. Application validation and network restrictions must enforce the approved route together.

### 5. Select and validate embedding and generation roles independently

Embedding and generation are separate model selections and separate capability checks. They may share **one project-owned connection and credential** when the approved origin and authentication are the same. Otherwise, use separate connections.

Sharing a connection does not require the roles to use the same model, and successful generation does not establish that embeddings work.

For example, a customer gateway may expose both a chat model and an embedding model at one approved origin. The user can enter its credential once and select the two models separately. Inframeld still probes each required capability and validates the embedding dimensions.

#### Test what the selected role actually needs

An **OpenAI-compatible** label does not guarantee support for every operation or model feature. Run bounded probes of the required chat and/or embedding capabilities rather than assuming full compatibility.

Reject incompatible responses, incorrect embedding dimensions, non-finite numerical values, invalid candidate or citation identities, and unsupported operations. Non-finite values include numbers such as infinity or “not a number”; they are not usable embedding coordinates. Candidate and citation identifiers must refer to valid application evidence, not invented identities.

Return **typed errors**: defined error outcomes the application and its clients can distinguish, rather than silently accepting an invalid result.

Replacing or removing a credential invalidates its previous role-validation status. A check performed with the old credential does not validate the new one. This changes connection usability, not the immutable semantics of an existing pipeline.

#### Evaluation setup is not a prerequisite for the first answer

The default onboarding path in [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) requires embedding and generation setup, but neither a judge role nor a benchmark before the user asks a question. A benchmark is the set of test cases used for evaluation.

The faithfulness judge remains part of v1 evaluation. **OpenEvals and configurable GPT-5.6 Luna are selected for qualification in [ADR-0008](ADR-0008-deterministic-evaluation-and-release-decisions.md).** Qualification means testing that the selected integration meets the requirements; selection is not evidence that those tests have passed.

### 6. Save provider credentials through a dedicated application API

Only an authorized credential operation may write, rotate, test, or remove a secret. Ordinary model operations use the configured connection; they do not become credential-management operations.

An authorized user can create, replace, and remove a persistent provider credential through the application API. Responses contain only safe metadata, not the saved secret. The eventual onboarding interface calls that API; **backend implementation comes first**.

#### Selected storage mechanism

[ADR-0020](ADR-0020-persistent-outbound-credentials.md) selects a narrow adapter that stores **authenticated ciphertext in PostgreSQL using PyNaCl**, with a separately supplied persistent deployment key.

Authenticated ciphertext protects the stored value through encryption and integrity checking. Business records contain credential references and safe connection metadata; the credential adapter owns the encrypted representation.

Both application-entered persistence and this storage choice are accepted. Implementation tests are still required. No vault service or cloud dependency is selected.

Mounted files remain useful for root and infrastructure secrets, including the separately supplied deployment key. **Mounted provider references alone are not a sufficient implementation:** users must be able to save provider credentials through the running application.

#### Resolve credentials for accepted work, not from job payloads

An **admitted operation** is work the application has accepted for execution. Resolve the credential for that operation using its connection identity.

```text
Accepted operation identifies its configured connection
    -> Resolve the associated credential for that operation
        -> Call the approved endpoint through ModelGateway
```

Workers receive connection identities, not secret-bearing job payloads or human authentication tokens. Never log provider secrets, put them in manifests, or return them in operation-status responses. A manifest is a recorded inventory of processing or index artifacts, not a secret store.

An owner-authenticated provider-secret upload returns a **sanitized terminal response**: a final operation result that does not echo the submitted secret. ADR-0007 specifies the separate key-creation response exceptions and keyed fingerprint rules.

### 7. Fail explicitly and keep retry decisions in one place

**A missing credential or provider failure must never trigger automatic fallback to another provider or model.** The selected connection and model are part of the requested behavior, not optional hints.

If credential replacement breaks a connection, old evidence remains intact while new calls fail explicitly. The same principle applies when a required credential has been removed.

Retry policy is owned centrally under ADR-0007. Disable framework or SDK retries that would independently repeat an **ambiguous provider call**: a call whose outcome is unknown, such as when the response is lost after the request may already have reached the provider.

A retry is not made safe merely because a library performs it. Application modules and evaluation libraries must not introduce another retry path outside the central policy.

### 8. Make the actual data path visible

Using a customer-managed gateway does not remove the need to explain what is sent. Display the actual connection, operation, and data path.

| Activity | Data path that must be disclosed |
| --- | --- |
| **Build an index using OpenAI embeddings** | Newly embedded chunk text is sent to OpenAI. Across the build, this may cover the whole corpus—the selected body of documents. |
| **Ask a question** | The question is sent for embedding. Selected permitted excerpts and instructions are sent to the configured generation endpoint. |
| **Run the faithfulness judge** | The configured question, answer, and evidence go through `ModelGateway` to the judge connection. These are additional model operations that must be explicitly disclosed. |
| **Store and search in Chroma** | Chroma receives embeddings and the configured chunk text/metadata. Local Chroma keeps them on the self-hosted server; future Chroma Cloud is a separate external processor. |
| **Use a local model endpoint** | Model processing stays within the configured local environment. Identity setup or model-asset setup may still involve network activity. |

**Do not describe all local use as universally “no egress.”** The claim must match the actual installation and operation, not just the fact that one model endpoint is local.

The local processing ports described earlier do not change this rule: any future remote processing must disclose its own data path.

### 9. Verify the integration before calling it supported

Choose and pin the LiteLLM release during implementation, then verify the behavior against that release. This ADR does not pin an untested SDK version.

| Area | Required verification |
| --- | --- |
| **Private endpoint support** | Exercise an OpenAI-compatible private test server using a custom CA and configured egress allowlists. |
| **Provider mappings** | Exercise the selected OpenAI and Ollama mappings through the embedded adapter. |
| **Response validation** | Reject malformed or incompatible responses, wrong embedding dimensions, non-finite values, invalid identities, and unsupported operations. |
| **Independent role validation** | Verify chat and embeddings separately. Successful generation must not be treated as proof of working embeddings or correct dimensions. |
| **Credential lifecycle** | Test persistent storage and rotation. Replacing/removing a credential invalidates old role-validation status without rewriting pipeline semantics. |
| **No implicit rerouting** | Verify that missing credentials and provider failures do not select another provider/model, and that an origin change does not implicitly forward an existing key. |
| **Gateway ownership** | Test evaluator attempts to bypass `ModelGateway`; no independent provider client or framework retry may evade the shared rules. |

These are acceptance requirements, not claims that implementation qualification has already passed.

## Consequences

### Positive

- **Model access has one application-owned boundary.** Generation, embeddings, classification using an LLM, and evaluation calls follow the same connection, credential, and retry rules rather than maintaining competing provider integrations.
- **Customers can use their own infrastructure in OSS.** Public providers, approved private gateways, local endpoints, custom CA trust, and customer credentials do not require an EE license, a separate proxy service, or an Inframeld-funded provider account.
- **Credential maintenance does not rewrite configuration history.** Immutable connection revisions preserve model meaning, while credentials can be replaced separately. Embedding and generation can share a connection without duplicate credential entry when their origin and authentication match.

### Negative

- **Custom endpoint support requires security and compatibility work.** URL checks alone are insufficient, and an OpenAI-compatible label does not prove every required operation works. Destination enforcement, custom trust, capability probes, and response validation must be implemented and tested.
- **Persistent credentials create storage and operational responsibilities.** The encrypted adapter, persistent deployment key, authorized management operations, and secret-free jobs/logs/responses all need verification. Rotation can invalidate a role's previously working access.
- **Availability cannot be preserved by silently changing the request.** Missing credentials, incompatible responses, or provider failures remain visible failures rather than triggering another model. A recorded external alias also cannot guarantee an unchanged underlying model.

## Alternatives considered

No separate comparative assessment is recorded. The approaches below are excluded or not required by this decision.

### Let each feature or evaluation library create its own provider client

**Ruled out.** Independent clients could bypass the shared connection, credential, endpoint, and retry rules. All LLM calls use `ModelGateway`, including calls made on behalf of third-party evaluation libraries.

### Require a separate LiteLLM Proxy service

**Not required.** The initial adapter uses the embedded LiteLLM Python SDK. A customer enterprise gateway remains an approved endpoint behind that adapter, not a reason to add another mandatory Inframeld service.

Alternative adapters may implement the same application port without changing this ownership rule.

### Reserve custom endpoints and customer credentials for EE

**Ruled out.** These capabilities and the core release loop belong in Apache-2.0 OSS. Future EE routing or administration features cannot make basic customer model access depend on `/ee`, a licensing server, or a platform-funded account.

### Allow arbitrary request URLs, or prohibit all private endpoints

**Neither approach is selected.** Arbitrary query/evaluation URLs would let ordinary callers direct outbound server requests. Banning every private address would prevent the required customer-gateway use case.

Deployment-approved origins, explicit private-network allowlisting, actual-destination validation, and network restrictions provide the selected boundary.

### Support provider credentials only through mounted references

**Insufficient for the product requirement.** Mounted files remain useful for root and infrastructure secrets, but users must be able to persist provider credentials through the application API.

The selected implementation uses PostgreSQL/PyNaCl and a separately supplied persistent deployment key. It does not require a vault service or cloud secret store.

## References

### Related decisions

| Reference | Responsibility |
| --- | --- |
| [ADR-0003: Lineage](ADR-0003-immutable-rag-lineage-and-release-identities.md) | Immutable model/configuration lineage and the distinction between semantic changes and credential rotation. |
| ADR-0007 | Central retry policy, ambiguous provider calls, key-creation response exceptions, and keyed fingerprints. |
| [ADR-0008: Evaluation](ADR-0008-deterministic-evaluation-and-release-decisions.md) | Faithfulness evaluation, OpenEvals, and the configurable judge selected for qualification. |
| [ADR-0010: Ingestion](ADR-0010-secure-document-ingestion-boundary.md) | Document-processing boundaries. |
| [ADR-0019: Default onboarding](ADR-0019-default-onboarding-and-first-publication.md) | Initial embedding/generation setup without a required judge role or benchmark. |
| [ADR-0020: Persistent outbound credentials](ADR-0020-persistent-outbound-credentials.md) | The narrow encrypted PostgreSQL/PyNaCl credential adapter. |

### Recorded external evidence

The source ADR records the following evidence as checked on **19 September 2026**. These references support the implementation direction; they are not completed Inframeld compatibility or security tests.

[LiteLLM's OpenAI-compatible endpoint documentation](https://docs.litellm.ai/docs/providers/openai_compatible) describes routing through a configured API base. The recorded evidence establishes adapter feasibility, not compatibility with every enterprise gateway.

[OWASP's SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html) supports allowlisting and validation at both application and network boundaries. The specific private-endpoint policy in this ADR is Inframeld's design.
