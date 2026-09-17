# Contributing to Inframeld

Thanks for helping improve Inframeld. The project is an early MVP, so small, focused pull requests and clear architectural reasoning are especially useful.

## Before you start

Install the repository toolchain with mise:

```bash
mise install
```

Then install dependencies:

```bash
pnpm install --frozen-lockfile
uv sync --project apps/backend --locked
```

Do not commit secrets, local environment files, generated build output, or personal editor state.

## Development workflow

1. Read the relevant architecture section and ADRs before changing a boundary.
2. Keep API behavior in the backend and treat the generated OpenAPI document as a reviewed contract artifact.
3. Add or update tests with behavior changes.
4. Run the complete local gate:

   ```bash
   pnpm check
   pnpm build
   ```

5. Regenerate and review the OpenAPI contract when an API surface changes:

   ```bash
   pnpm openapi
   pnpm openapi:check
   ```

6. Use the guided Conventional Commit workflow:

   ```bash
   pnpm commit
   ```

## Pull requests

Keep pull requests focused. Describe the problem, the chosen approach, the validation you ran, and any follow-up work. If a change alters a durable architectural decision, add or update an ADR in `docs/adr`.

Pull requests should make clear whether they change:

- public API or OpenAPI behavior;
- persistence, tenancy, authorization, or security boundaries;
- generated artifacts or release behavior; or
- user-facing web behavior.

CI must pass before merge. Maintainers may request narrower commits or an ADR when a change crosses one of the documented boundaries.

## Dependency updates

JavaScript and GitHub Actions updates are managed through Dependabot. Python dependencies are managed with uv. From the repository root, update them with:

```bash
uv lock --upgrade --project apps/backend
uv sync --locked --project apps/backend
```

Commit the resulting `uv.lock` changes only when the resolution passes the configured release-age policy.
