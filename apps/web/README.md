# Inframeld web app

The web app is a Next.js App Router client for the Inframeld API. It is a thin client: product behavior and API models remain owned by the backend contract.

## Development

From the repository root:

```bash
pnpm --filter @inframeld/web dev
```

The app is available at <http://localhost:3000>.

## Checks

```bash
pnpm --filter @inframeld/web lint
pnpm --filter @inframeld/web format:check
pnpm --filter @inframeld/web typecheck
pnpm --filter @inframeld/web build
```

Type checking uses TypeScript 7 through the `@typescript/native` package alias. The `typescript` alias supplies Microsoft's TypeScript 6 compatibility API for ESLint and other API consumers, following [Microsoft's side-by-side guidance](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/#running-side-by-side-with-typescript-6.0). Keep both aliases when updating compiler and lint tooling.

UI components are managed with shadcn/ui. Add a component with:

```bash
pnpm dlx shadcn@latest add button
```
