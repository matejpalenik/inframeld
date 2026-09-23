# Inframeld

![CodeRabbit Pull Request Reviews](https://img.shields.io/coderabbit/prs/github/matejpalenik/inframeld?utm_source=oss&utm_medium=github&utm_campaign=matejpalenik%2Finframeld&labelColor=171717&color=FF570A&link=https%3A%2F%2Fcoderabbit.ai&label=CodeRabbit+Reviews)

Inframeld is an open-source platform for configuring models, uploading knowledge, and asking grounded questions.

It provides versioned knowledge, benchmark comparisons, and governed releases when you need more control over how a RAG pipeline reaches production.

## Quick start

### 1. Install the toolchain

The supported toolchain is declared in `mise.toml`:

```bash
mise install
```

This installs the versions of Node.js, pnpm, Python, and uv used by the repository.

### 2. Install dependencies

```bash
pnpm install --frozen-lockfile
uv sync --project apps/backend --locked
```

### 3. Configure the backend

On your first setup, create the local backend environment file:

```bash
cp apps/backend/.env.example apps/backend/.env
```

### 4. Start PostgreSQL and run migrations

```bash
pnpm dev:db
pnpm --filter @inframeld/backend migrate
```

### 5. Start Inframeld

```bash
pnpm dev
```

The applications are now available at:

- Web: http://localhost:3000
- API: http://127.0.0.1:8000
- API documentation: http://127.0.0.1:8000/docs

See the [backend README](apps/backend/README.md) for database management, migrations, configuration, and running the backend through Compose.

## Repository layout

Inframeld is intentionally structured as a small monorepo so the API, web client, generated contract, architecture decisions, and delivery checks can evolve together.

| Path                | Purpose                                           |
| ------------------- | ------------------------------------------------- |
| `apps/backend`      | Typed FastAPI application and OpenAPI export      |
| `apps/web`          | Next.js App Router web client                     |
| `contracts/openapi` | Committed API contract generated from FastAPI     |
| `docs`              | Architecture, development documentation, and ADRs |

## Development

Run both applications from the repository root:

```bash
pnpm dev
```

To run individual applications:

```bash
pnpm --filter @inframeld/web dev
pnpm --filter @inframeld/backend dev
```

To regenerate the OpenAPI contract:

```bash
pnpm openapi
```

For backend-specific development, see the [backend README](apps/backend/README.md).

## Quality checks

Run the complete local gate before opening a pull request:

```bash
pnpm check
pnpm build
```

`pnpm check` runs formatting checks, linting, type checking, tests, and verifies that the committed OpenAPI document matches the FastAPI application.

Commit messages follow Conventional Commits. Use the guided commit prompt:

```bash
pnpm commit
```

## Architecture

Start with the [developer architecture guide](docs/ARCHITECTURE.md) for an overview of the system and its boundaries.

For more detail:

- [Architecture decision records](docs/adr/README.md) document individual architectural decisions.
- [v1 architecture review](docs/reviews/v1-architecture-review.md) records the v1 scope assessment and remaining bounded choices.
- [AGENTS.md](AGENTS.md) defines the repository's read-only AI guidance for developers who write the implementation by hand.
- [Repository skills plan](docs/development/repository-skills-plan.md) documents the coverage, usage, and maintenance of the six domain skills under `.agents/skills/`.

Architecture documentation describes both implemented and planned behavior. An accepted design does not necessarily mean that behavior has already been implemented or qualified.

Backend implementation comes first. External SDK Kit suitability blocks Studio development, whose primary client remains the official generated TypeScript SDK.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow.

Security vulnerabilities should be reported according to [SECURITY.md](SECURITY.md).

## License

Inframeld is available under the [Apache License 2.0](LICENSE).
