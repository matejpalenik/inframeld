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

FastAPI/Pydantic owns the native OpenAPI 3.1.x schema. From the root, `pnpm --filter @inframeld/backend openapi` exports the committed artifact. `pnpm --filter @inframeld/backend openapi:check` checks drift without regenerating it. An approved HTTP change updates the route/model first, then its generated contract. Never hand-edit a competing schema or handwritten application client. The client generator remains unselected. See [HTTP and generated clients](../../../.agents/skills/inframeld-application-contracts/references/http-mcp-and-generated-clients.md).

The [Kratos identity schema](../../../config/kratos/identity.schema.json) retains its own published identity and draft. Runtime settings, Compose definitions and lockfiles own executable configuration and pins. Avoid copied version tables.

<a id="design-only-envelopes"></a>

## Design-only envelopes

[Maintenance](../../../contracts/design/access/maintenance-v1.schema.json) and [version 2 recovery evidence](../../../contracts/design/access/recovery-event-v2.schema.json) formalize accepted input shapes. The [version 1 recovery draft](../../../contracts/design/access/recovery-event-v1.schema.json) is superseded and retained as historical design, without a runtime compatibility path. They are not runtime models, OpenAPI endpoints, trusted provider evidence or production qualification. Their owning Access references describe parsing, byte limits and authority that JSON Schema cannot prove. Future implementation must reconcile or supersede these handwritten design schemas with runtime-owned definitions.

For a concrete implemented example, inspect [CurrentSessionResponse](../../../apps/backend/src/inframeld_backend/access/http/responses/current_session_response.py), the [session route](../../../apps/backend/src/inframeld_backend/access/http/routes/current_session_routes.py) and [0001_initial](../../../apps/backend/migrations/versions/0001_initial.py). The first two define the delivered human-session representation. The migration owns the foundational database constraints.
