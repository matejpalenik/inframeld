# Inframeld documentation

The documentation site uses the Tailwind Plus Protocol template with Next.js App Router and MDX. The original template license is preserved in [LICENSE.md](LICENSE.md).

Run these commands from the repository root:

```sh
pnpm dev:docs         # http://localhost:3001
pnpm build:docs       # Production build
pnpm start:docs       # Serve a completed build on port 3001
pnpm check:docs       # Format, lint, typecheck, content tests, and production build
```

Use `pnpm --filter @inframeld/docs format` to format only this application. Node and pnpm follow the root repository's pinned versions. Install dependencies from the repository root with `pnpm install`.

## Write a page

The canonical user documentation lives in `src/app/**/page.mdx`. Add a route there and an entry in `src/lib/navigation.json`. Do not create a second user guide under `docs/user`. Internal engineering documents remain in the repository's `docs/development` tree.

Export `pageMetadata` with a title and description. Add a server `layout.tsx` in a new route directory that exports this value as `metadata`, following the existing guide. This keeps Next.js metadata in the server layout while content stays in MDX. Start with the reader's task, state prerequisites, then show a complete request and explain its outcomes. Verify capability claims against the current implementation. State when a CLI command or package distribution is unavailable.

The MDX components include `Note`, `Button`, `CodeGroup`, `Row`, `Col`, `Properties`, and `Property`. Prefer ordinary Markdown headings, links, tables, and fenced code. Use the repository's `inframeld-documentation` skill for writing guidance.

## Verify a change

`pnpm check:docs` runs the complete application gate. Individual checks are also available:

```sh
pnpm --filter @inframeld/docs format:check
pnpm --filter @inframeld/docs lint
pnpm --filter @inframeld/docs typecheck
pnpm --filter @inframeld/docs content:check
pnpm --filter @inframeld/docs test
pnpm --filter @inframeld/docs build
```

Typecheck generates Next.js route types before running TypeScript, so it works in a fresh checkout without an earlier build. Content checks compile MDX and check local page links, section anchors, public assets, and navigation destinations. They do not fetch external sites or execute SDK examples. Changes to examples need source inspection and the relevant SDK checks as well.

The `--webpack` flag is required for development and builds: the Protocol search module creates a FlexSearch index through a custom Webpack loader. Theme switching, mobile navigation, section tracking, code tabs, and search remain part of the template. New documentation content is indexed at build time and during development.

The first guide describes original request lookup implemented in PR #273. Its examples were checked against the generated SDK surfaces and controlled local responses; this does not establish live installation or PostgreSQL behavior.
