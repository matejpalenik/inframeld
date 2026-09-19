# ADR-0018: First-party MCP access to deployed knowledge

**Status:** Accepted — consuming interface and supported-client profile; SDK and interoperability qualification pending.
**Date:** 19 September 2026.
**Required approach:** Two tools in the existing API process, using the same application behavior as HTTP and trusted clients that manage bearer credentials and idempotency keys. Universal OAuth interoperability and delegated-user access are outside this decision.
**Related:** [API contract](ADR-0002-product-owned-openapi-contract.md), [authorization](ADR-0005-api-enforced-tenancy-and-authorization.md), [model gateway](ADR-0006-byok-provider-boundary.md), [idempotency](ADR-0007-durable-jobs-idempotency-and-recovery.md), [canaries](ADR-0009-sticky-logical-canary-deployments.md).

## Context

An engineer connects a trusted AI application to Inframeld so it can ask questions of an already deployed pipeline and receive answers with evidence. **MCP**, the Model Context Protocol, provides a tool-based interface for that interaction.

A **pipeline** retrieves document evidence and uses it to generate an answer. A **Deployment** selects the pipeline version that serves requests. MCP provides another way to request that existing behavior; it does not create another retrieval engine or a new place to manage releases.

From first principles, **changing the transport must not change the caller's permissions, the version-selection rules, or whether a retry repeats a chargeable model call**. The MCP adapter must therefore reuse the same application operations and security rules as the HTTP API.

The client matters too. The initial integration assumes a trusted installed or server-side application that can attach credentials to every request and control retry keys outside the model's discretion. Supporting that profile does not establish compatibility with every product that offers a “connect MCP server” screen.

## Decision

**Expose `query_deployment` and `get_answer_receipt` through the official Python MCP SDK, mounted inside the existing backend process. Authenticate the whole MCP interface with Inframeld's existing integration-credential verifier, then invoke the ordinary application use cases.**

The first tool produces an answer through the deployed pipeline. The second reads the safe record of an existing answer operation without regenerating or replaying its text.

The two-tool interface and trusted-client profile are accepted. **Qualification means testing the selected SDK integration and named client versions; it is not another approval step for this scope or evidence that the implementation already works.** No additional identity stack, universal OAuth connection flow, or verified end-user delegation is included.

### 1. Keep MCP at the application boundary

An **incoming adapter** translates a transport request into an application operation and translates the result back. The MCP adapter has that responsibility, not ownership of pipeline configuration, authorization, retrieval, generation, or release state.

```text
Trusted client sends an authenticated MCP request
    -> MCP adapter validates and translates the request
        -> Existing application use case, with verified access context
            -> Query: normal routing, authorized retrieval, and ModelGateway
            -> Receipt: authorized read of existing status and evidence identities
        <- Application-owned result
    <- MCP structured result and matching text representation
```

A **use case** implements an application operation, such as querying a Deployment. The **access context** identifies the verified caller and applicable scope. `ModelGateway` is Inframeld's shared interface for model calls.

Domain and application code must not import MCP SDK types. The **composition root**, the code that connects concrete dependencies to application operations, supplies the use cases, request access context, and infrastructure dependencies.

#### Share behavior without confusing the two wire contracts

The existing OpenAPI document remains the HTTP contract. MCP has its own protocol envelopes and generated tool JSON Schemas. An **envelope** is the protocol's message structure; a **JSON Schema** describes the allowed fields and types.

Those MCP schemas are transport representations of the same application request/result types. Add parity tests proving equivalent business behavior through HTTP and MCP.

Do not automatically turn every OpenAPI operation into a tool. Reuse also does not mean sending an OpenAPI document over MCP or making an internal HTTP request with a copied user token. Invoke the application use case directly through the adapter.

### 2. Expose exactly two application tools

| Tool                     | Inputs and result                                                                                                                                                                                                                        | Application behavior                                                                                                                                         |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **`query_deployment`**   | Accepts `deploymentId`, a bounded `question`, required `idempotencyKey`, and optional `affinityKey`. First success returns the answer, citations, `answerId`, operation identity, and selected pipeline version and Deployment revision. | Resolve project and permissions on the server, select the current or canary version once, retrieve authorized evidence, and generate through `ModelGateway`. |
| **`get_answer_receipt`** | Accepts `answerId`. Returns the existing safe receipt/status, selected version, and currently authorized citation identities.                                                                                                            | Read an existing receipt under current authorization. Do not regenerate the answer or return cached answer text or source snippets.                          |

An **answer receipt** is the bounded record of an answer's execution and outcome, not a stored copy of its full response. An **operation identity** identifies the accepted work independently of an individual network request.

The query's affinity key is required when candidate traffic is enabled, as explained in Section 4. The recommended project-default selector adds a conditional `projectId` requirement, described separately in Section 7.

#### A receipt ID is a reference, not permission

The receipt tool accepts only identities owned by the authenticated principal within its permitted scope. A **principal** is the stable human or application identity recognized by Inframeld. An opaque ID does not grant access merely because a client knows it.

Use the same receipt-access policy as HTTP. Check every source identity bound to the final generation context, including sources that were used but not cited. The **final generation context** is the evidence supplied to the model to produce that answer.

If the receipt is inaccessible, deny it rather than return a partial result that reveals protected document metadata. Missing and inaccessible resources have the same safe outward result wherever distinguishing them would reveal existence.

#### Receipts support recovery, not general job administration

A client that already knows `answerId` can inspect its receipt without resending the question. If the first response was lost before the client learned that ID, it retries the original query key to obtain the known receipt or pending/uncertain outcome.

This is the existing query-recovery behavior. It does not add a generic job-administration tool.

Include sufficient permitted citations in the first answer. Defer raw document/chunk enumeration, standalone search, arbitrary downloads, and additional citation-content tools until a concrete client requires them. Any later detail tool must reuse current document authorization: an S3 storage key or historical citation must not become a public download.

Answer feedback uses [ADR-0017's HTTP contract](ADR-0017-answer-feedback.md). Do not automatically add a model-driven feedback tool. Build, evaluation, promotion, rollback, membership, and credential-management tools are also outside this initial interface.

### 3. Authenticate a preconfigured application on every request

An authorized administrator creates the existing scoped, expiring, revocable **opaque integration credential**. Opaque means the secret is verified by Inframeld rather than interpreted as a caller-authored claim about identity or permissions.

The installed or server-side client stores it outside prompts and source control, and sends this header on **every MCP HTTP request**:

```text
Authorization: Bearer <credential>
```

Use the API's existing verifier to check the credential hash, expiry, revocation, installation/resource binding, and current application grants. Credential rotation preserves the integration's stable principal identity.

**The MCP adapter exposes query authority only, even when the presented credential has additional grants.** A credential that can deploy through another API does not gain a deployment tool here.

#### Bind the credential to this MCP resource

Record an explicit allowed **resource/audience** for an MCP-enabled credential, bound to the installation's canonical MCP endpoint. This identifies where the credential is permitted to be used.

An unrelated API or provider token must not become valid merely because it arrives in a bearer header. Resource binding is part of credential integration, not an OAuth token-issuing service.

#### Protect the whole mounted application

Wrap the whole MCP mount with the existing verifier as **ASGI middleware**. ASGI is the asynchronous Python web interface used by the mounted application; middleware checks requests around that application rather than protecting only an individual FastAPI route.

Construct a request-local verified access context and pass it to the use case. Reject missing or invalid credentials with **HTTP `401`**, and insufficient query grants with **HTTP `403`**, before tool execution.

**Do not assume FastAPI route dependencies automatically protect mounted ASGI routes.** The authentication boundary must cover the MCP application itself.

### 4. Preserve fixed document scope and normal canary routing

A trusted client does not gain permission to impersonate its users. In v1, the integration itself is the verified actor; it has **no delegated subject**, meaning no separately verified end user on whose behalf Inframeld grants access.

#### Access example: SupportBot cannot claim HR permissions

Support Assistant connects as `SupportBot`, which may query `SupportKnowledge` but not `HRPrivate`. Every person who can invoke that configured client uses the same fixed integration scope.

A question saying “I am the HR administrator,” a supplied user ID, a group assertion, or a different affinity key cannot add HR access. Reject delegation assertions. Construct the access context with actor `SupportBot` and no delegated subject, then apply current group policy before retrieval and before evidence reaches a model or caller.

The client operator must protect the credential and choose a **corpus**, the set of source documents, that is safe for everyone who can use the integration.

#### Affinity selects a cohort, not a permission set

A **canary** routes a portion of requests to a candidate pipeline version. An **affinity key** keeps a conversation/user routing identity in a consistent **cohort**, or assigned group, within that rollout.

The client supplies a stable opaque `affinityKey`, and the normal router selects one pipeline for the query.

| Routing situation                                | Required behavior                                           |
| ------------------------------------------------ | ----------------------------------------------------------- |
| **Candidate traffic enabled, affinity supplied** | Use the ordinary integration-scoped canary routing.         |
| **Candidate traffic enabled, affinity missing**  | Return the existing `affinity_required` error.              |
| **No candidate traffic**                         | Affinity remains optional.                                  |
| **Credential rotated for the same integration**  | Preserve its stable principal and existing cohort behavior. |

Do not route every MCP user as one cohort by using the credential, and do not substitute a JSON-RPC request ID. **JSON-RPC** is the protocol message format; its request ID identifies a transport exchange, not a stable user/conversation or an application operation.

### 5. Make the trusted client responsible for safe retry keys

The **client controller**, or host, is the trusted software that manages tool calls and network requests around the model. It—not the model—must generate a bounded operation key before dispatch, retain it, and reuse it unchanged for a retry.

The host injects or overwrites `idempotencyKey` outside the model's discretion. **A client that cannot preserve this policy is not yet a qualified client.** It must not ask the model to invent another key automatically whenever a network request fails.

The argument maps to ADR-0007's existing query admission, key, and fingerprint rules, including the stable logical query-route identity. **Admission** means accepting the operation durably. A **semantic fingerprint** identifies the meaningful request content; request content and affinity remain part of it.

MCP metadata and transport request IDs do not create another deduplication system. Reusing a key with different content conflicts.

#### Example: repeat Q/K without paying for another answer

SupportBot sends question **Q** with key **K**, receives an answer, and retains it. Repeating Q/K returns the recorded receipt with **`responseAvailable: false`**, without another model call.

If the first answer was lost in transit, that receipt still reports completion. It cannot reconstruct the missing answer text.

| Operation state                         | What the retry reports                                                                             |
| --------------------------------------- | -------------------------------------------------------------------------------------------------- |
| **Completed**                           | The known receipt/status with `responseAvailable: false`, not a regenerated or cached full answer. |
| **Still running**                       | Its operation identity and the existing bounded retry guidance.                                    |
| **Provider outcome uncertain**          | `recovery_required`, without automatically dispatching another model request.                      |
| **A deliberately new key is submitted** | A new query that may incur another charge. This is not an automatic repair for a lost answer.      |

Key expiry and disaster-restore limits remain those of [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md). MCP does not extend the underlying retention or deduplication guarantee.

A disconnect or cancellation attempts to stop remaining local work safely. It cannot undo a provider call already dispatched. Retain the known or uncertain operation outcome and follow the normal gateway retry policy. No MCP-specific full-response cache or durable task engine is added.

### 6. Make answers, receipts, and errors distinguishable to clients

Declare input/output schemas and return **`structuredContent`**, the machine-readable tool result, accompanied by a concise text representation of the same result.

Both representations must distinguish a first successful answer, a safe replay, and a failure or uncertain outcome. **Do not present a receipt as an empty successful answer or suggest that the client should automatically ask again with a new key.**

| Failure boundary                                             | Representation                                                                                                                                    |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Missing/invalid credentials or insufficient query grants** | HTTP `401` or `403` before tool execution.                                                                                                        |
| **Malformed protocol request**                               | The SDK's protocol error handling. Do not implement another JSON-RPC parser.                                                                      |
| **Application failure**                                      | Sanitized tool result with `isError: true`, a stable application error code, an optional operation identity, and retry guidance where applicable. |

Never expose exception traces, secret configuration, cross-project identifiers, or provider request bodies.

#### Describe query effects conservatively

Use these annotations for `query_deployment`:

| Annotation            | Value   | Why                                                                                                                             |
| --------------------- | ------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **`readOnlyHint`**    | `false` | The call creates an operation/receipt and consumes a model budget.                                                              |
| **`destructiveHint`** | `false` | The tool requests an answer rather than a destructive administrative change.                                                    |
| **`idempotentHint`**  | `false` | Deduplication depends on the explicit key and its documented lifetime; repeated tool calls are not unconditionally effect-free. |
| **`openWorldHint`**   | `true`  | Answering can involve the configured external model connection.                                                                 |

Describe costs and data egress in the tool description. **Egress** means data leaving an environment for another recipient. The receipt read can be marked read-only.

Annotations are hints. They grant no permissions and do not authorize repeating a paid query. “Consumes knowledge” must not be mistaken for “free and without side effects.”

### 7. Support the recommended project-default selector without another tool

The default onboarding path in [ADR-0019](ADR-0019-default-onboarding-and-first-publication.md) recommends a logical default selector for the same deployed-query use case:

```json
{
  "deploymentId": "default",
  "projectId": "<project ID>"
}
```

This illustrates the **recommended selector fields**, not a complete query request; `question` and `idempotencyKey` remain required by the query contract.

`projectId` is required for this selector. Ordinary opaque Deployment IDs keep their existing meaning.

The common resolver checks project/query permission before revealing setup state. Before first publication, it returns a typed not-ready result—a defined outcome clients can recognize—instead of invoking a different answer path.

The selector supports default **Automatic updates** and reversible publication modes through normal Deployment resolution. It adds no third tool, publication-mode administration, alternate retriever, or unverified identity. Test equivalent default resolution through HTTP and MCP.

The two-tool scope is accepted; **this exact selector shape remains a recommendation**, not an additional finalized wire contract.

### 8. Mount the official SDK inside the existing API process

The source records its protocol and SDK research on **19 September 2026**. Preserve those versioned choices as the basis for qualification, not as evidence of a working Inframeld integration or a fresh upstream verification.

| Component                        | Recorded evidence and implementation direction                                                                                                                                                |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **MCP protocol**                 | The source records `latest` as the released **2026-07-28** revision with stateless requests, not a release candidate or draft. Recommend it as the primary wire version.                      |
| **Official Python SDK**          | The source records **`mcp 2.2.0`**, released **7 September 2026**, under MIT, with 2.x current and **1.30.0** the maintenance line. Initially qualify a pinned 2.2.0 dependency.              |
| **Older protocol compatibility** | Recommend **2025-11-25** only as a limited compatibility profile handled by the SDK, not as the latest protocol.                                                                              |
| **Hosting support**              | Tagged 2.2.0 documentation describes mounting its Starlette ASGI application in FastAPI, with the parent starting the MCP session manager's lifespan.                                         |
| **Reference client support**     | Tagged 2.2.0 documentation accepts an application-supplied HTTP client carrying authorization headers. This establishes a specific integration direction, not universal client compatibility. |

Earlier 2.0-alpha advice is superseded by the stable SDK release recorded in the source. A stable upstream release still does not establish that Inframeld's integration is correct.

#### Use one canonical HTTPS endpoint and the parent lifespan

Mount one MCP ASGI application behind the existing TLS reverse proxy at:

```text
https://<installation>/mcp/
```

TLS protects the HTTPS connection; the reverse proxy is the installation's existing public traffic entry point.

Use **`MCPServer.streamable_http_app()`** with **`json_response=True`**. Set **`stateless_http=True`** for the SDK's older-protocol compatibility path.

Construct the sub-application before accessing its session manager. Enter **`mcp.session_manager.run()`** from FastAPI's existing lifespan—the startup/shutdown lifecycle. The mounted sub-application's own lifespan is insufficient. Preserve the normal API routes and shutdown order.

Use the official SDK rather than adding a second community wrapper framework.

#### Stateless transport does not require another persistence system

For the source's selected **2026-07-28** protocol, requests have no initialization session or `Mcp-Session-Id`. The SDK's stateless setting applies to its older protocol path.

Do not add session persistence, sticky load balancing, or an event store. Neither tool requires an old standalone HTTP+SSE endpoint, a stdio server, subscriptions, sampling, elicitation, MCP Tasks, or resumable response streams. SSE means server-sent events; stdio uses process input/output streams.

Advertise only implemented capabilities. Let the SDK validate required per-request protocol metadata and matching HTTP method/name/version headers before any use case executes.

Bound request bodies, question length, response size, admission concurrency, and deadlines consistently with the HTTP query endpoint. Non-streaming JSON returns the answer when complete; **it does not remove provider latency or permit requests to run without a deadline**.

### 9. Enforce host, origin, and network restrictions

Use explicit **`TransportSecuritySettings`** with DNS-rebinding protection enabled, allowed installation hostnames, and exact allowed origins. DNS rebinding is a risk involving a hostname resolving to a different destination; the selected SDK checks must remain enabled.

| Boundary                           | Required behavior                                                                                                                                       |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`Host` and `Origin` validation** | Configure allowed installation hosts and exact origins. Reject an invalid present `Origin`; do not fix validation failures by disabling the protection. |
| **Requests without `Origin`**      | Installed/server clients may omit it. Its absence does not bypass authentication.                                                                       |
| **Proxy and container exposure**   | Keep API container ports private. Trust forwarded headers only from the configured proxy.                                                               |
| **Canonical URL**                  | Configure the final HTTPS URL, including the endpoint path, to avoid accidental redirects.                                                              |
| **Local trial**                    | Restrict exposure to loopback, the local machine's network interface.                                                                                   |
| **Cross-origin browser access**    | Not included in this initial installed/server-client profile. Do not add wildcard CORS or store integration secrets in the browser.                     |

**CORS**, cross-origin resource sharing, controls browser requests between origins. Later browser MCP support needs explicit qualification of exact origins, preflight headers, and secret handling. A preflight is the browser's preliminary permission-check request.

If an older client path uses an MCP protocol session identifier, it is never an authentication credential, an end-user identity, or a canary affinity value.

### 10. State the client-compatibility and OAuth limits explicitly

The reference client is the official Python SDK **2.2.0** with a configured **`httpx2.AsyncClient`** passed to **`streamable_http_client`**. In that recorded 2.x integration, authorization headers belong on the supplied HTTP client.

Add other named clients to a tested compatibility list only when their versions demonstrate header injection, supported protocol behavior, and safe retry handling. **No desktop-client integration is certified by this decision.**

#### A bearer secret is not the complete OAuth connection flow

The protocol makes authorization optional and says HTTP implementations supporting it should follow its authorization specification. The initial preconfigured-header profile is **not full MCP OAuth authorization interoperability**.

That interoperable flow includes protected-resource metadata, authorization-server discovery, resource-bound OAuth tokens, and client registration. Public-client authorization also requires **PKCE**, Proof Key for Code Exchange, a protection used in the authorization flow. A static secret in an HTTP header does not implement those facilities.

The recorded SDK's built-in OAuth **`TokenVerifier`** configuration also requires **`AuthSettings`**, including an issuer, and advertises protected-resource discovery. Do not supply fictitious issuer settings or point them at Kratos merely to use that configuration.

**Kratos's external OIDC sign-in does not make it an OAuth access-token issuer.** OIDC is the sign-in protocol used for human identity here. The MCP mount instead uses the existing application verifier without advertising a discovery flow that does not exist.

If broad browser-based OAuth connection becomes a v1 requirement, that changes the scope: select a real authorization-server integration, discovery/registration, consent, and token lifecycle, then qualify the target clients. The issuer need not run in the MCP server, but cannot be omitted by relabelling an opaque application key.

Hydra and verified end-user delegation remain deferred unless separately approved. Human engineers continue using Kratos sessions in Inframeld; do not export their session cookies to MCP clients. A later named OAuth-only client requirement is a new scope decision, not an implied obligation to deploy Hydra now.

### 11. Keep credentials, model execution, and returned content in their proper boundaries

Never accept credentials in tool arguments, URL query parameters, or document content. Never forward the caller's integration token, upstream OIDC token, or Kratos session to `ModelGateway` or another MCP server.

Inframeld resolves its own approved model-connection credentials. A future OAuth adapter must validate issuer, audience, and scope before constructing the same application access context.

Every model call **made by Inframeld**, including query embedding and answer generation, continues through `ModelGateway`. Embedding converts the question into numerical values used for search. No MCP sampling asks the consuming client to perform an Inframeld model step.

The consuming host may itself send returned knowledge to its own model. That is a **separate external recipient controlled by the client's operator**, and the connection documentation must disclose it. Inframeld's internal gateway policy does not imply control over everything a consuming host does with a permitted answer.

Source text remains untrusted evidence, not instructions that grant tools, credentials, or permissions. Do not put question text, excerpts, or tokens in transport or audit logs.

### 12. Test the deployed integration before claiming client support

| Area                                      | Required qualification                                                                                                                                                                                                                                     |
| ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Hosting and lifecycle**                 | Run real HTTP tests through the TLS proxy and mounted FastAPI lifespan. Exercise startup, shutdown, and exact endpoint paths. An in-memory SDK test does not test the deployed authentication boundary.                                                    |
| **Protocol and limits**                   | Test current-version metadata/header mismatches, unsupported versions, legacy stateless negotiation, bounded bodies/timeouts, and absence of unintended tools/capabilities. Verify JSON and structured-result handling with each supported client version. |
| **Authentication and transport security** | Test missing, expired, revoked, wrong-resource, and insufficient-scope tokens; invalid Host/Origin; missing Origin with valid server-client credentials; and rejection of cookie-only access.                                                              |
| **Scope and application parity**          | Reject forged users/groups and cross-project Deployment/receipt IDs. Prove HTTP/MCP equivalence for group revocation, deleted citations, model-gateway routing, canary affinity, missing affinity, and credential rotation.                                |
| **Retries and interrupted requests**      | Race identical query keys, disconnect before and after provider dispatch, retry completed queries, and change input under the same key. Verify no automatic second model call and no durable full-answer replay cache.                                     |
| **Receipts and credential boundaries**    | Read receipts after permission revocation and verify that clients visibly distinguish receipt-only and uncertain outcomes. Ensure tokens and secret-bearing provider details never cross their intended boundaries.                                        |
| **Default selector**                      | Verify that HTTP and MCP share permission checks, default-target resolution, and the not-ready outcome.                                                                                                                                                    |

These are future acceptance cases, not completed tests or a new general certification suite. No MCP server implementation, client interoperability test, security test, or operational qualification was performed by the source documentation change.

## Consequences

### Positive

- **MCP uses the product's existing behavior.** Queries and receipts share application ownership, permissions, routing, model access, and retry semantics with HTTP rather than creating a second implementation.
- **The runtime stays small.** Two tools run in the existing API process through the official SDK, without another service, identity issuer, session store, or task engine.
- **Clients receive explicit evidence and recovery outcomes.** First answers carry citations and identities; retries report known status without silently repeating model work or exposing a hidden full-answer archive.

### Negative

- **Compatibility is deliberately limited.** Clients must attach authorization headers and preserve host-controlled retry keys. An OAuth-only connection screen cannot be assumed to work, and named clients need version-specific tests.
- **A lost full answer may remain lost.** A receipt can report completion but cannot recover its text. Clients needing the answer must retain their successful response; a new query is a separate potentially chargeable operation.
- **An adapter still needs security and protocol work.** Whole-mount authentication, resource binding, lifespan integration, schemas, result variants, limits, and HTTP/MCP parity require implementation and testing. Fixed application access also cannot enforce distinct rights for unverified end users behind the same credential.

## Alternatives considered

The source excludes or defers the approaches below. It does not record a separate comparative evaluation.

### Expose every OpenAPI operation automatically as an MCP tool

**Ruled out.** The initial interface deliberately contains only deployed queries and receipt reads. Administration, standalone retrieval, document enumeration/downloads, and additional citation tools need a concrete requirement and their existing authorization boundaries. Feedback stays on its accepted HTTP interface.

### Create another retrieval implementation or proxy every tool through internal HTTP

**Not selected.** The MCP adapter invokes the existing application use cases directly. It does not own retrieval or release state, and reuse does not mean copying a caller's token into an internal HTTP request. Domain/application contracts remain independent of the MCP SDK.

### Add another MCP framework, process, or persistence system

**Not required.** Mount the official SDK in the existing backend and use its protocol handling. No second wrapper framework, session persistence, sticky load balancing, event store, durable MCP task engine, or full-response cache is needed for these tools.

### Claim universal OAuth compatibility from a static bearer credential

**Ruled out.** Resource-bound opaque credentials serve the selected preconfigured client profile, not the complete OAuth discovery/registration flow. Kratos is not substituted for a missing OAuth issuer. Hydra, delegated users, and broader browser-based connection flows remain separate scope decisions.

### Let the model choose new retry keys after network failures

**Ruled out.** The trusted controller creates and preserves the operation key outside the model's discretion. A new key can authorize another paid query; it is not a safe automatic recovery mechanism for an unanswered network request.

## References

### Related decisions

| Reference                                                                            | Responsibility                                                                                                            |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| [ADR-0002: API contract](ADR-0002-product-owned-openapi-contract.md)                 | The HTTP contract and shared application request/result behavior.                                                         |
| [ADR-0005: Authorization](ADR-0005-api-enforced-tenancy-and-authorization.md)        | Integration credentials, fixed application authority, current document permissions, and the deferred delegation boundary. |
| [ADR-0006: Model gateway](ADR-0006-byok-provider-boundary.md)                        | Model-call ownership, approved credentials/endpoints, and data egress.                                                    |
| [ADR-0007: Idempotency](ADR-0007-durable-jobs-idempotency-and-recovery.md)           | Query admission, fingerprints, receipt-only retries, uncertainty, key lifetime, and restore limits.                       |
| [ADR-0009: Canaries](ADR-0009-sticky-logical-canary-deployments.md)                  | Stable integration-scoped affinity and selection of one pipeline version per query.                                       |
| [ADR-0017: Answer feedback](ADR-0017-answer-feedback.md)                             | The existing HTTP feedback contract; no additional feedback tool is selected here.                                        |
| [ADR-0019: Default onboarding](ADR-0019-default-onboarding-and-first-publication.md) | The recommended project-default selector and ordinary serving behavior across publication modes.                          |

### Recorded external evidence

The original ADR records these official references as checked on **19 September 2026**. Their version and capability observations are preserved here; they have not been freshly verified or demonstrated by an Inframeld integration test as part of this rewrite.

| Reference group                | Recorded evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Protocol release**           | [2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28) and [release announcement](https://blog.modelcontextprotocol.io/posts/2026-07-28/).                                                                                                                                                                                                                                                                                                                                                 |
| **SDK release**                | [`mcp 2.2.0` on PyPI](https://pypi.org/project/mcp/2.2.0/), [SDK 2.2.0 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.2.0), and [1.30.0 maintenance release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.30.0).                                                                                                                                                                                                                                                      |
| **Hosting and lifecycle**      | [Tagged ASGI mounting guide](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/run/asgi.md), [hosting example](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs_src/asgi/tutorial002.py), and [transport options](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/run/index.md).                                                                                                                                                                                |
| **Transport and clients**      | [Versioned Streamable HTTP rules](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/streamable-http), [tagged deployment behavior](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/run/deploy.md), and [client transport guidance](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/client/transports.md).                                                                                                                                                |
| **Security and authorization** | [Tagged transport-security implementation](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/src/mcp/server/transport_security.py), [SDK authorization contract](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/run/authorization.md), [protocol authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), and [PKCE/security requirements](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization/security-considerations). |
| **Tools and results**          | [Tool result/error contract](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) and [annotation definitions](https://modelcontextprotocol.io/specification/2026-07-28/schema#toolannotations).                                                                                                                                                                                                                                                                                                       |
