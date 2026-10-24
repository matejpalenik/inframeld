# Share behavior across HTTP, MCP and generated clients

SupportBot should receive the same permission, serving selection and retry outcome whether a supported adapter uses HTTP or MCP. HTTP carries ordinary web/API requests. Model Context Protocol (MCP) lets an assistant client call the accepted tools. Transport changes how input arrives. It must not create another authority or execution model.

## Follow a request across adapters

1. Parse and validate transport input. Authentication establishes a verified application-owned context rather than trusting tool arguments or caller-supplied groups.
2. Invoke the owning application service. The service coordinates current authority, transactions or external work and produces application-owned outcomes.
3. Convert those outcomes into the transport's documented success/error shape. Keep stable operation IDs, native error declarations, bounded pagination, asynchronous outcomes and answer-versus-receipt-only variants.

Feature HTTP conversions use static Mapper methods without I/O. Routes serialize, dependencies extract and invoke, middleware wraps lifecycle. Business fingerprint meaning stays in the application service. Adapters must not introduce another permission engine, retry engine or automatic default-resource implementation.

## Native OpenAPI and clients

OpenAPI is the machine-readable description of the HTTP operations and their inputs/results. Selected FastAPI/Pydantic output is authoritative native OpenAPI 3.1.x. Do not hand-edit generated output, weaken backend semantics for a generator or build a custom generator by implication. V1 delivers a Rust CLI and small Ory account UI. Full Studio is deferred and later uses its generated TypeScript client and the same CLI-led product rules.

Generate application clients from native OpenAPI without prescribing a generator package or adding a replacement handwritten client. Qualify incrementally against implemented contracts. Intended language targets are not qualified deliverables. Ory's clients serve Ory contracts, not a second Inframeld API. Historical client reviews do not establish current interoperability.

Browser writes preserve user-session/CSRF protection. Server rendering retains the user's context without a global administrator key or cache shared between users. Backend work proceeds independently of deferred Studio.

The RFC 9457 error foundation and shared pagination models are implemented foundations. Each feature still checks cursor contents, scope and current authorization. Shared limits are 1–100 with default 25. Deterministic feature ordering includes a unique tie-breaker. Another page is an explicitly bounded request, not permission to traverse everything.

## MCP's deliberately small profile

MCP exposes only `query_deployment` and `get_answer_receipt` in the existing API process. Authenticate every mounted request. Mounting does not automatically inherit HTTP protection. Reuse ordinary application authorization, version selection, ModelGateway and business idempotency keys.

The selected SDK route uses a low-level `Server` and explicit tool-argument validation. It advertises no prompts, resources or subscriptions. Header-capable preconfigured trusted clients are supported. Human CLI Hydra login does not add universal OAuth discovery, third-party onboarding, verified per-user delegation or administrative tools. Tool arguments cannot establish credentials, and MCP request IDs cannot replace business retry identity.

Compare HTTP/MCP parity by exact scope, selected version/input, receipt identity and outcome. No extra tools follow from Evaluation, onboarding, feedback or diagnostics. Follow each owner's contracts when exposing supported behavior.

## Authentication and delivery status

Human HTTP cookie/bearer dispatch, current provider/local checks and native problem/challenge declarations have implementation evidence. Current human routes implement `invalid_authentication_request` and native cookie-or-bearer security alternatives. Separate real-provider tests do not establish a complete account UI, CLI lifecycle, application authenticator or verified recovery. API-audience human tokens do not become MCP credentials. Application-session routes and later maintenance/recovery wires remain accepted design/drafts where identified.

The application-connection wizard uses ordinary account/grant/key operations. It neither exports human credentials nor automatically issues a key at setup. Show-once delivery, partial outcomes and separately approved paid testing retain ordinary recovery rules.

- [API contracts](../../../../docs/development/api-contracts.md), [MCP](../../../../docs/development/mcp.md), [error handling](../../../../docs/development/error-handling.md), [error maintainer reference](../../../../docs/development/error-handling-reference.md), [pagination](../../../../docs/development/pagination.md) and [CLI delivery](../../../../docs/development/cli-delivery-plan.md).
- [ADR-0003](../../../../docs/adr/ADR-0003-generate-the-authoritative-openapi-contract-from-backend-code.md), [ADR-0006](../../../../docs/adr/ADR-0006-use-official-generated-clients-for-application-api-access.md), [ADR-0053](../../../../docs/adr/ADR-0053-use-kratos-and-hydra-for-human-cli-authentication.md), [ADR-0055](../../../../docs/adr/ADR-0055-deliver-cli-first-v1-through-openapi-generated-clients.md) and [Access contracts](../../../../docs/development/access-contracts.md).
