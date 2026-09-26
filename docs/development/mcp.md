# Using Inframeld through MCP

A trusted installed or server-side client can ask Inframeld questions through MCP. Assume it connects as SupportBot and queries Production. Everyone using that client gets SupportBot's current document access. A prompt cannot give the request another person's permissions.

**MCP** means Model Context Protocol. It carries the tool calls described here. [API contracts](api-contracts.md) explains the shared application behavior, and [jobs and retries](jobs-and-idempotency.md) explains recovery after a lost response.

Start with the two supported tools, then follow authentication and retry handling. The later sections record the selected protocol, client requirements, and work still needing verification.

> **Design status:** This is the accepted v1 client profile. The protocol and SDK choices are dated research, not proof that an Inframeld integration or a named client has passed testing.

## Contents

| Reader’s question | Start here |
| --- | --- |
| Does MCP implement another query engine? | [1. Keep the adapter thin](#model) |
| What may a client ask Inframeld to do? | [2. Invoke the two supported tools](#tools) |
| How are credentials and scope checked? | [3. Authenticate every mounted request](#authentication) |
| What if the tool response is lost? | [4. Distinguish an answer from recovery status](#retries) |
| Does onboarding need another tool? | [5. Resolve the ordinary default route](#defaults) |
| Which transport and client are qualified? | [6. Mount and protect the official SDK](#hosting) |
| What must a supported client demonstrate? | [7. Maintainer checks](#maintainer-checks) |
| Why these choices, and what remains open? | [8. Decision and reference map](#decision-map) |

<a id="model"></a>

## 1. Keep the adapter thin

The MCP adapter translates a tool call into an existing application operation and translates the result back. It does not take over pipeline configuration, permissions, retrieval, answer generation, or releases.

```text
Trusted client sends an authenticated MCP request
    -> MCP adapter validates and translates the request
        -> Existing application use case, with verified access context
            -> Query: normal routing, authorized retrieval, and ModelGateway
            -> Receipt: authorized read of existing status and evidence identities
        <- Application-owned result
    <- MCP structured result and matching text representation
```

A **use case** performs the application operation, such as querying Production. Its **access context** identifies the verified caller and permitted project or resources. ModelGateway remains the shared path for model calls.

Domain and application code use their own types, without importing MCP SDK types. Startup wiring, called the **composition root**, supplies the use cases and infrastructure. Each request supplies its own verified caller context.

### Share behavior without confusing the two wire contracts

OpenAPI continues to describe HTTP. MCP uses its own message structure, or **envelope**, and tool **JSON Schemas** that describe allowed fields and types.

The MCP schemas represent the same application inputs and results. Tests must show that equivalent HTTP and MCP calls produce equivalent business behavior.

Expose only the selected tools, rather than converting every OpenAPI endpoint. The adapter calls the application directly. It neither sends OpenAPI as MCP messages nor makes an internal HTTP call using a copied user token.

<a id="tools"></a>

## 2. Invoke the two supported tools

| Tool | Inputs and result | Application behavior |
| --- | --- | --- |
| **`query_deployment`** | Accepts `deploymentId`, a bounded `question`, required `idempotencyKey`, and optional `affinityKey`. First success returns the answer, citations, `answerId`, operation identity, and selected pipeline version and Deployment revision. | Resolve project and permissions on the server, select the current or canary version once, retrieve authorized evidence, and generate through `ModelGateway`. |
| **`get_answer_receipt`** | Accepts `answerId`. Returns the existing safe receipt/status, selected version, and currently authorized citation identities. | Read an existing receipt under current authorization. Do not regenerate the answer or return cached answer text or source snippets. |

An **answer receipt** records what happened during an answer request without saving its full response. An **operation ID** identifies the accepted work even if several network requests try to obtain its result.

The query needs an affinity key when candidate traffic is enabled. This keeps related requests on the same trial version, as explained under [authentication and routing](mcp.md#authentication). The recommended [default selector](mcp.md#defaults) also needs `projectId`.

### A receipt ID is a reference, not permission

The receipt must belong to the authenticated principal and be within its current permitted scope. A **principal** is the stable identity of a human or application. Knowing an opaque receipt ID does not grant access.

Use the same receipt checks as HTTP. Check every source sent to the model for its final answer, including sources that influenced it without being cited.

Deny an inaccessible receipt rather than return partial metadata about private documents. Where even existence is private, missing and inaccessible resources must have the same safe outward result.

### Receipts support recovery, not general job administration

A client that knows `answerId` can read the receipt directly. If the answer response was lost before the client learned that ID, it repeats the original query key to find the receipt or the pending or uncertain outcome.

This is the existing query-recovery behavior. It does not add a generic job-administration tool.

The first answer should contain sufficient permitted citations. Raw document or chunk lists, standalone search, arbitrary downloads, and further citation-content tools wait for a concrete client need. Any later tool must check current access. A historical citation or S3 object key must never become a public download link by itself.

Feedback uses the [existing HTTP contract](answer-feedback.md). V1 adds no model-driven feedback tool, or tools for builds, evaluation, releases, membership, or credentials.

<a id="authentication"></a>

## 3. Authenticate every mounted request

An authorized administrator creates an existing Inframeld application key with a defined scope, expiry, and revocation support. The key is **opaque**: Inframeld verifies it rather than trusting identity or permission claims written by the caller.

The installed or server-side client stores it outside prompts and source control, and sends this header on **every MCP HTTP request**:

```text
Authorization: Bearer <credential>
```

The existing API verifier checks the key's hash, expiry, revocation, permitted installation and resource, and the account's current permissions. Replacing the key keeps the same application principal.

A key with additional permissions still gets only this adapter's query and receipt tools. Permission to deploy through another API does not create a deployment tool here.

### Bind the credential to this MCP resource

An MCP-enabled key needs an explicit allowed **resource or audience**, tied to the installation's canonical MCP endpoint. This says where the key may be used.

Putting an unrelated API or provider token in a bearer header does not make it valid. Checking a key's intended endpoint does not require an OAuth token-issuing service.

### Protect the whole mounted application

Protect the entire mounted MCP application with the existing verifier through **ASGI middleware**. ASGI is the Python web interface used by the mount. Middleware checks requests around the whole application, including paths outside an individual FastAPI route.

For each request, construct a fresh verified access context and pass it to the use case. Return HTTP `401` for absent or invalid credentials and HTTP `403` for insufficient query permissions before running the tool.

**Do not assume FastAPI route dependencies automatically protect mounted ASGI routes.** The authentication boundary must cover the MCP application itself.

All calls use SupportBot's current group memberships, with no delegated human identity. Reject user or group claims supplied by the client. Candidate traffic requires an affinity key, but that key affects routing only. Key replacement preserves the principal's rollout group. See [application access](access-control.md#applications) and [canary routing](pipelines-and-releases.md#manual).

Credentials belong in authentication headers, never tool arguments, URLs, or documents. Incoming tokens must not be forwarded to ModelGateway. Explain that the client host may send permitted answers to its own model, which is a separate external recipient outside Inframeld's control. Keep questions, excerpts, and tokens out of transport and audit logs.

<a id="retries"></a>

## 4. Distinguish an answer from recovery status

The **host**, or client controller, is the trusted software that sends tool calls around the model. It creates the operation key before sending the request, enforces its size limit, saves it, and reuses it for retries.

The host supplies or overwrites `idempotencyKey`. The model cannot choose another key to retry a failed network request. A client that cannot enforce this rule has not met the supported-client requirements.

The key follows the normal [request acceptance and fingerprint rules](jobs-and-idempotency.md). A fingerprint summarizes meaningful input so the backend can recognize the same request. It includes the question content and affinity, and uses the stable logical query route.

MCP metadata and request IDs do not replace that business request key. Reusing it with different content is a conflict.

### Example: repeat Q/K without paying for another answer

SupportBot sends question **Q** with key **K**, receives an answer, and retains it. Repeating Q/K returns the recorded receipt with **`responseAvailable: false`**, without another model call.

If the first answer was lost in transit, that receipt still reports completion. It cannot reconstruct the missing answer text.

| Operation state | What the retry reports |
| --- | --- |
| **Completed** | The known receipt/status with `responseAvailable: false`, not a regenerated or cached full answer. |
| **Still running** | Its operation identity and the existing bounded retry guidance. |
| **Provider outcome uncertain** | `recovery_required`, without automatically dispatching another model request. |
| **A deliberately new key is submitted** | A new query that may incur another charge. This is not an automatic repair for a lost answer. |

The [shared retry rules](jobs-and-idempotency.md) still determine key expiry and what a disaster restore can recover. MCP does not extend those guarantees.

Disconnecting or canceling asks the backend to stop remaining local work safely. It cannot undo a provider call already sent. Save the known or uncertain outcome and follow the normal ModelGateway retry policy. MCP adds no full-answer cache or separate durable task engine.

### Make answers, receipts, and errors distinguishable to clients

Declare tool input and output schemas. Return the machine-readable result as **`structuredContent`**, with a concise text version containing the same meaning.

Both versions must clearly identify a first answer, a receipt-only retry, a failure, or an uncertain outcome. Never display a receipt as an empty successful answer or tell the client to retry automatically with a new key.

| Failure boundary | Representation |
| --- | --- |
| **Missing/invalid credentials or insufficient query grants** | HTTP `401` or `403` before tool execution. |
| **Malformed protocol request** | The SDK's protocol error handling. Do not implement another JSON-RPC parser. |
| **Application failure** | Sanitized tool result with `isError: true`, a stable application error code, an optional operation identity, and retry guidance where applicable. |

Never expose exception traces, secret configuration, cross-project identifiers, or provider request bodies.

### Describe query effects conservatively

Use these annotations for `query_deployment`:

| Annotation | Value | Why |
| --- | --- | --- |
| **`readOnlyHint`** | `false` | The call creates an operation/receipt and consumes a model budget. |
| **`destructiveHint`** | `false` | The tool requests an answer rather than a destructive administrative change. |
| **`idempotentHint`** | `false` | Deduplication depends on the explicit key and its documented lifetime. Repeated tool calls are not unconditionally effect-free. |
| **`openWorldHint`** | `true` | Answering can involve the configured external model connection. |

The tool description must explain costs and where data may be sent outside the installation. This outgoing transfer is called **egress**. The receipt read can be marked read-only.

Annotations are hints for clients, not permissions or approval to repeat paid work. Reading knowledge through a model may still have costs and external effects.

<a id="defaults"></a>

## 5. Resolve the ordinary default route

The default onboarding path in [From a new account to a first useful answer](onboarding.md) recommends a logical default selector for the same deployed-query use case:

```json
{
  "deploymentId": "default",
  "projectId": "<project ID>"
}
```

These are recommended selector fields, not a complete request. `question` and `idempotencyKey` are still required.

`projectId` is required for this selector. Ordinary opaque Deployment IDs keep their existing meaning.

The shared resolver checks project membership and Query permission before showing setup state. If no first version has been published, it returns a defined not-ready outcome. It does not answer through a separate fallback path.

The selector reaches the default Deployment through normal resolution, including Automatic updates and later mode switches. It adds no third tool, mode administration, separate retrieval path, or unverified identity. Test that HTTP and MCP resolve it equivalently.

The two-tool interface is accepted. The exact selector fields remain a recommendation, not a finalized additional wire contract.

<a id="hosting"></a>

## 6. Mount and protect the official SDK

The recorded research is dated **19 September 2026**. These version choices define what the integration must be tested against. They are neither a fresh check of upstream releases nor evidence that the Inframeld integration works.

| Component | Recorded evidence and implementation direction |
| --- | --- |
| **MCP protocol** | The source records `latest` as the released **2026-07-28** revision with stateless requests, not a release candidate or draft. Recommend it as the primary wire version. |
| **Official Python SDK** | The source records **`mcp 2.2.0`**, released **7 September 2026**, under MIT, with 2.x current and **1.30.0** the maintenance line. Initially qualify a pinned 2.2.0 dependency. |
| **Older protocol compatibility** | Recommend **2025-11-25** only as a limited compatibility profile handled by the SDK, not as the latest protocol. |
| **Hosting support** | Tagged 2.2.0 documentation describes mounting its Starlette ASGI application in FastAPI, with the parent starting the MCP session manager's lifespan. |
| **Reference client support** | Tagged 2.2.0 documentation accepts an application-supplied HTTP client carrying authorization headers. This establishes a specific integration direction, not universal client compatibility. |

The source's stable SDK choice supersedes its earlier 2.0-alpha advice. A stable library release still needs testing within Inframeld.

### Use one canonical HTTPS endpoint and the parent lifespan

Mount one MCP ASGI application behind the existing TLS reverse proxy at:

```text
https://<installation>/mcp/
```

TLS protects the HTTPS connection. The reverse proxy is the installation's existing public entry point.

Use the official SDK's low-level **`Server`** with only **`on_list_tools`** and **`on_call_tool`** handlers. In the [pinned SDK 2.2.0](https://github.com/modelcontextprotocol/python-sdk/blob/v2.2.0/docs/advanced/low-level-server.md), the higher-level `MCPServer` advertises prompts, resources, and subscriptions even when Inframeld registers no such content. The low-level server advertises only the handler families it serves. Validate tool arguments against their advertised schemas before calling the application, because the low-level server does not do that validation automatically.

Create the sub-application with **`server.streamable_http_app(json_response=True, stateless_http=True)`**. The stateless setting supports the SDK's older-protocol compatibility path.

Create the sub-application before accessing its session manager. Run **`server.session_manager.run()`** inside FastAPI's existing startup/shutdown lifecycle, called its lifespan. The mounted application's lifespan alone does not do this. Keep the normal API routes and shutdown order.

Use the official SDK rather than adding a second community wrapper framework.

### Stateless transport does not require another persistence system

Under the selected **2026-07-28** protocol, requests have no initialization session or `Mcp-Session-Id`. The SDK's stateless setting is for compatibility with older protocol versions.

No session store, sticky load balancing, or event store is needed. Neither tool requires the old standalone HTTP+SSE endpoint, a stdio server, subscriptions, sampling, elicitation, MCP Tasks, or resumable response streams. SSE sends server events over HTTP. Stdio uses a process's input and output streams.

Advertise only capabilities that have been implemented. Before calling a use case, let the SDK validate the protocol metadata and matching HTTP method, name, and version headers.

Apply the same request-body, question-length, response-size, simultaneous-request, and deadline limits as HTTP queries. Non-streaming JSON returns the answer once complete. It still waits for the provider and still needs a deadline.

### Enforce host, origin, and network restrictions

Set explicit **`TransportSecuritySettings`** with DNS-rebinding protection, allowed installation hostnames, and exact allowed origins. DNS rebinding can make a hostname resolve to a different destination. Keep the SDK's selected protection enabled.

| Boundary | Required behavior |
| --- | --- |
| **`Host` and `Origin` validation** | Configure allowed installation hosts and exact origins. Reject an invalid present `Origin`. Do not fix validation failures by disabling the protection. |
| **Requests without `Origin`** | Installed/server clients may omit it. Its absence does not bypass authentication. |
| **Proxy and container exposure** | Keep API container ports private. Trust forwarded headers only from the configured proxy. |
| **Canonical URL** | Configure the final HTTPS URL, including the endpoint path, to avoid accidental redirects. |
| **Local trial** | Restrict exposure to loopback, the local machine's network interface. |
| **Cross-origin browser access** | Not included in this initial installed/server-client profile. Do not add wildcard CORS or store integration secrets in the browser. |

Browser MCP support remains work to verify later. It needs exact origins, preflight headers, and safe secret handling. **CORS** controls browser requests across origins, and a **preflight** is the browser's preliminary permission-check request.

If an older client uses an MCP session ID, that ID proves neither authentication nor human identity. It is not a canary-affinity value either.

### State the client-compatibility and OAuth limits explicitly

The reference client is the official Python SDK **2.2.0** with a configured **`httpx2.AsyncClient`** passed to **`streamable_http_client`**. In that recorded 2.x integration, authorization headers belong on the supplied HTTP client.

Add a named client to the compatibility list only after testing its version for authentication headers, protocol support, and safe retries. No desktop-client integration is certified by this decision.

### A bearer secret is not the complete OAuth connection flow

The protocol makes authorization optional and says HTTP implementations supporting it should follow its authorization specification. The initial preconfigured-header profile does **not** provide full MCP OAuth interoperability.

Full OAuth connection includes finding the protected resource and authorization server, registering the client, and issuing tokens bound to the resource. Public clients also need **PKCE**, a protection for the authorization exchange. A static key in a header does not implement these facilities.

The recorded SDK's built-in OAuth `TokenVerifier` also requires `AuthSettings`, including an issuer, and advertises resource discovery. Do not invent an issuer or point this setting at Kratos merely to enable that configuration.

Kratos's company OIDC sign-in identifies humans. It does not make Kratos an OAuth access-token issuer. The MCP mount therefore uses Inframeld's existing application-key verifier without advertising an unavailable OAuth discovery flow.

If broad browser OAuth connection becomes a v1 requirement, make a new scope decision. It needs a real authorization server, discovery and registration, consent, token lifecycle, and tested clients. That issuer can run elsewhere, but renaming an opaque application key cannot replace it.

Hydra and verified user delegation remain deferred unless separately approved. Human engineers use Kratos sessions inside Inframeld and must not export those cookies to MCP clients. Supporting a later OAuth-only client needs its own decision.

<a id="maintainer-checks"></a>

## 7. Maintainer checks

| Area | Required qualification |
| --- | --- |
| **Hosting and lifecycle** | Run real HTTP tests through the TLS proxy and mounted FastAPI lifespan. Exercise startup, shutdown, and exact endpoint paths. An in-memory SDK test does not test the deployed authentication boundary. |
| **Protocol and limits** | Test current-version metadata/header mismatches, unsupported versions, legacy stateless negotiation, and bounded bodies/timeouts. Confirm discovery advertises only tools, rejects unsupported prompt/resource/subscription calls, and validates malformed tool arguments. Verify JSON and structured-result handling with each supported client version. |
| **Authentication and transport security** | Test missing, expired, revoked, wrong-resource, and insufficient-scope tokens, invalid Host/Origin, missing Origin with valid server-client credentials, and rejection of cookie-only access. |
| **Scope and application parity** | Reject forged users/groups and cross-project Deployment/receipt IDs. Prove HTTP/MCP equivalence for group revocation, deleted citations, model-gateway routing, canary affinity, missing affinity, and credential rotation. |
| **Retries and interrupted requests** | Race identical query keys, disconnect before and after provider dispatch, retry completed queries, and change input under the same key. Verify no automatic second model call and no durable full-answer replay cache. |
| **Receipts and credential boundaries** | Read receipts after permission revocation and verify that clients visibly distinguish receipt-only and uncertain outcomes. Ensure tokens and secret-bearing provider details never cross their intended boundaries. |
| **Default selector** | Verify that HTTP and MCP share permission checks, default-target resolution, and the not-ready outcome. |

The cases below are requirements for the future integration. The source documentation change implemented no MCP server and ran no interoperability, security, or operational tests. It also introduced no general certification framework.

<a id="decision-map"></a>

## 8. Decision and reference map

Protocol 2026-07-28 and Python SDK 2.2.0 remain the dated choices to test, not newly verified releases. The default-selector fields are still recommended. Browser OAuth discovery, Hydra, delegated users, broader tools, and certification of named desktop clients remain outside this profile.

| Decision | Rationale |
| --- | --- |
| [ADR-0044](../adr/ADR-0044-provide-mcp-through-a-thin-adapter-in-the-existing-api-process.md) | Provide MCP through a thin adapter in the existing API process. |
| [ADR-0045](../adr/ADR-0045-support-preconfigured-mcp-clients-with-application-credentials.md) | Support preconfigured MCP clients with application credentials. |
