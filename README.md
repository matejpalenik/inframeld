# Inframeld

Inframeld is an open-source MVP for a governed RAG release loop: versioned knowledge, deterministic evaluation, reviewable promotion, and traceable answers.

The repository is intentionally structured as a small monorepo so the API, web client, generated contract, architecture decisions, and delivery checks can evolve together.

## Repository layout

| Path                | Purpose                                       |
| ------------------- | --------------------------------------------- |
| `apps/backend`      | Typed FastAPI application and OpenAPI export  |
| `apps/web`          | Next.js App Router web client                 |
| `contracts/openapi` | Committed API contract generated from FastAPI |
| `docs`              | Architecture specification and ADRs           |

## Prerequisites

The supported toolchain is declared in `mise.toml`:

```bash
mise install
```

This installs Node.js, pnpm, Python, and uv at the versions used by the repository checks.

## Setup

```bash
pnpm install --frozen-lockfile
uv sync --project apps/backend --locked
```

## Development

Run both applications from the repository root:

```bash
pnpm dev
```

The web app runs at <http://localhost:3000> and the backend runs at <http://127.0.0.1:8000>.

Useful focused commands:

```bash
pnpm --filter @inframeld/web dev
pnpm --filter @inframeld/backend dev
pnpm openapi
```

## Quality checks

Run the complete local gate before opening a pull request:

```bash
pnpm check
pnpm build
```

`pnpm check` checks formatting, lints, type-checks, tests, and verifies that the committed OpenAPI document matches the FastAPI application.

Commit messages follow Conventional Commits. Use the guided commit prompt:

```bash
pnpm commit
```

## Architecture

Start with the [MVP governed RAG release-loop architecture](docs/2026-09-17-mvp-governed-rag-release-loop-architecture.md) and its [architecture decision records](docs/adr/README.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow and [SECURITY.md](SECURITY.md) for vulnerability reporting.

## License

Inframeld is available under the [Apache License 2.0](LICENSE).
