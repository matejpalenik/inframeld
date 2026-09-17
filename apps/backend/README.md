# Inframeld backend

The backend is a typed FastAPI application. It owns the HTTP API, its generated OpenAPI document, and the contract tests that prevent API drift.

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
