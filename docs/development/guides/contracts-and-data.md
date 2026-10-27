# Find the contract that owns a field

<a id="find-the-contract-that-owns-a-field"></a>

Alice wants to know whether a grant request accepts a recipient UUID and which database relationship protects it. Those are related questions with different authorities. A logical record explains meaning. A Pydantic model defines the delivered HTTP shape. A migration defines the implemented database constraint.

| Question | Authority |
| --- | --- |
| What fields does an HTTP request or response have? | [Backend routes and models](../../../apps/backend/src/inframeld_backend/access/http) and [generated OpenAPI](../../../contracts/openapi/v1/inframeld-v1.json). |
| What does a domain value or service capability mean? | Its defining Python type under [the backend](../../../apps/backend/src/inframeld_backend) and the owning skill workflow. |
| Which tables, keys and indexes exist? | [Migrations](../../../apps/backend/migrations/versions), in order. ORM rows map the fields their adapter needs and are not a second schema definition. |
| Which logical relationships are accepted but not all implemented? | The domain record references below. A named concept does not imply one table, aggregate or endpoint. |
| What error can a caller receive? | [Public catalogue](../error-handling.md), implemented problem definitions and the relevant OpenAPI operation. |
| What is still undecided? | The owning skill’s conditional `decision-*.md` routes. A recommendation has no approval status. |

<a id="logical-records-by-owner"></a>

## Logical records by owner

- [Logical identity and grants](../../../.agents/skills/inframeld-access-models/references/identity-and-grant-records.md), [implemented Access models](../../../.agents/skills/inframeld-access-models/references/implemented-access-models.md), [Access persistence](../../../.agents/skills/inframeld-access-models/references/access-persistence.md) and [lifecycle writes](../../../.agents/skills/inframeld-access-models/references/access-lifecycle-persistence.md). Authentication has its own [credentials and recovery](../../../.agents/skills/inframeld-access-models/references/credential-and-recovery-records.md).
- [Knowledge](../../../.agents/skills/inframeld-knowledge/references/records.md) and [Indexing](../../../.agents/skills/inframeld-indexing/references/records.md).
- [Pipelines](../../../.agents/skills/inframeld-pipelines/references/records.md), [Evaluation](../../../.agents/skills/inframeld-evaluation/references/records.md) and [Releases](../../../.agents/skills/inframeld-releases/references/records-and-transitions.md).
- Shared [operation identity](../../../.agents/skills/inframeld-application-contracts/references/idempotency-and-replay.md), [jobs](../../../.agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md), [spending](../../../.agents/skills/inframeld-application-contracts/references/spending-and-accounting.md) and [artifacts](../../../.agents/skills/inframeld-application-contracts/references/artifact-storage.md).

<a id="generate-from-implementation"></a>

## Generate from implementation

FastAPI/Pydantic owns the native OpenAPI 3.1.x schema. From the root, `pnpm --filter @inframeld/backend openapi` exports the committed artifact. `pnpm --filter @inframeld/backend openapi:check` checks drift without regenerating it. An approved HTTP change updates the route/model first, then its generated contract. Never hand-edit a competing schema or handwritten application client. [ADR-0088](../../adr/ADR-0088-use-a-pinned-patched-generator-for-the-rust-sdk.md) selects the pinned patched Rust generator. [ADR-0089](../../adr/ADR-0089-select-patched-typescript-and-python-sdk-generators.md) selects the TypeScript and Python configurations. The [SDKs skill](../../../.agents/skills/inframeld-sdks/SKILL.md) owns common maintenance, with independent language skills for [Rust](../../../.agents/skills/inframeld-rust-sdk/SKILL.md), [TypeScript](../../../.agents/skills/inframeld-typescript-sdk/SKILL.md) and [Python](../../../.agents/skills/inframeld-python-sdk/SKILL.md) consumption and specific obligations. See [HTTP and generated clients](../../../.agents/skills/inframeld-application-contracts/references/http-mcp-and-generated-clients.md).

The [Rust SDK comparison](../reports/rust-sdk-generator-comparison.md) records two upstream generators and an isolated unpublished patched candidate, their shared HTTP scenarios and qualification limits. The [workspace guide](../../../packages/sdk-tools/README.md) explains regeneration, drift checks and local package consumption. The subsequent Rust selection is recorded separately from these observations. Generator selection is not a supported public SDK release.

The [TypeScript and Python comparison](../reports/typescript-python-sdk-generator-comparison.md) evaluates seven upstream options and three isolated patch experiments against common backend scenarios. The [current runbook](../../../packages/sdk-tools/README.md) covers selected SDK maintenance and package builds. Historical comparison reproduction is retired under ADR-0091. [ADR-0089](../../adr/ADR-0089-select-patched-typescript-and-python-sdk-generators.md) records the subsequent selection without changing those historical observations. [ADR-0090](../../adr/ADR-0090-qualify-sdks-with-shared-contract-scenarios.md) accepts shared three-SDK conformance. The unified SDK runner and operation-coverage gate are implemented. Automatic Linux checks cover applicable PRs, with macOS for generator changes and manual runs. Report actual platform execution separately, and configure external branch rules to require the SDK conformance aggregate. Application Contracts remains the HTTP compatibility owner.

The [Kratos identity schema](../../../config/kratos/identity.schema.json) retains its own published identity and draft. Runtime settings, Compose definitions and lockfiles own executable configuration and pins. Avoid copied version tables.

<a id="design-only-envelopes"></a>

## Design-only envelopes

[Maintenance](../../../contracts/design/access/maintenance-v1.schema.json) and [version 2 recovery evidence](../../../contracts/design/access/recovery-event-v2.schema.json) formalize accepted input shapes. The [version 1 recovery draft](../../../contracts/design/access/recovery-event-v1.schema.json) is superseded and retained as historical design, without a runtime compatibility path. They are not runtime models, OpenAPI endpoints, trusted provider evidence or production qualification. Their owning Access references describe parsing, byte limits and authority that JSON Schema cannot prove. The private v2 recovery mapper now owns runtime parsing and intentionally remains outside public OpenAPI. The design schema remains an explanatory artifact. Other future implementations must reconcile their handwritten design schemas with runtime-owned definitions.

For a concrete implemented example, inspect [CurrentSessionResponse](../../../apps/backend/src/inframeld_backend/access/http/responses/current_session_response.py), the [session route](../../../apps/backend/src/inframeld_backend/access/http/routes/current_session_routes.py) and [0001_initial](../../../apps/backend/migrations/versions/0001_initial.py). The first two define the delivered human-session representation. The migration owns the foundational database constraints.

SDK maintainers start with the [human architecture map](../../../packages/sdk-tools/docs/architecture.md) and [endpoint walkthrough](../../../packages/sdk-tools/docs/adding-endpoint.md). Shared feature tests inspect actual requests and native results across all five profiles. The tooling records delivered behavior without taking ownership of HTTP semantics or the pending server-version compatibility decision.
