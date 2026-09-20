# Inframeld backend

The backend is a typed FastAPI application. It owns the HTTP API, its generated OpenAPI document, and the contract tests that prevent API drift.

## Backend structure

The backend is a domain-first modular monolith. The top-level domain packages own business state and rules; they are not separate services:

```text
src/inframeld_backend/
├── access/       # principals, project scope, grants, authorization
├── knowledge/    # sources, document versions, collections, memberships
├── indexing/     # processing, embeddings, generations, materializations
├── pipelines/    # immutable RAG configuration, queries, receipts, feedback
├── evaluation/   # offline cases, runs, evidence, metrics, comparisons
├── releases/     # deployments, cohorts, promotion, rejection, rollback
├── shared/       # cross-cutting capabilities; no business-state ownership
├── composition.py
└── main.py
```

Each business package uses the onion-architecture rings below:

```text
knowledge/
├── domain/          # business rules and values
├── application/     # commands, queries, and application-owned ports
├── infrastructure/  # PostgreSQL and other external implementations
└── api/             # HTTP/MCP-facing adapters for this owner
```

Vertical slices live within those rings when a use case is implemented. Only create the slice's files when the corresponding use case is being implemented; do not pre-create generic repositories, services, or framework layers. Within a module, dependencies point inward:

```text
api -> application -> domain
infrastructure -> application-owned ports
composition.py -> concrete implementations and configuration
```

`shared` is restricted to capabilities used across domains, such as transport errors, configuration, database lifecycle, jobs, and idempotency. It must not become a second owner of domain state. The current health route is a cross-cutting HTTP adapter under `shared/http`; domain and application code may not import it. Shared technical capabilities use `domain/`, `application/`, and `infrastructure/` only where that separation is genuinely needed.

`main.py` is the process entry point. `composition.py` is the composition root: it constructs the application and explicitly wires concrete dependencies. HTTP, the future worker, Studio, and MCP must invoke the same application use cases; they must not implement parallel business behavior.

Architecture tests under `tests/architecture` protect these dependency rules. They use static import checks and fixtures that prove forbidden dependencies are rejected.

## Development

From the repository root:

```bash
pnpm --filter @inframeld/backend dev
```

The API is available at <http://127.0.0.1:8000>. FastAPI's interactive documentation is available at `/docs` and `/redoc`.

## Checks

```bash
pnpm --filter @inframeld/backend format:check
pnpm --filter @inframeld/backend lint
pnpm --filter @inframeld/backend typecheck
pnpm --filter @inframeld/backend test
pnpm --filter @inframeld/backend openapi:check
```

## OpenAPI

The application is the source of truth for the generated OpenAPI document. Export the committed contract with:

```bash
pnpm --filter @inframeld/backend openapi
```

The exported document lives at `contracts/openapi/v1/inframeld-v1.json` and is checked into the repository so clients and CI can review contract changes as ordinary source changes.
