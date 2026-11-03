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

Follow the approved [site structure](../../.agents/skills/inframeld-documentation/references/site-structure.md): Get started, Product, Guides, CLI and SDKs, API reference, Self-hosting, and Changelog and support. Keep these labels and their defined entries in order. The seven Guides entries link to detailed tasks. CLI has one child level for setup, configuration, commands and automation. Existing detailed routes remain reachable from the appropriate entries.

Export `pageMetadata` with a title and description. Add a server `layout.tsx` in a new route directory that exports this value as `metadata`, following the existing guide. This keeps Next.js metadata in the server layout while content stays in MDX. Start with the reader's task, give necessary prerequisites, then show a supported action and explain its outcome. Lead interactive CLI guides with ordinary output. Link shared setup from the client pages. Represent unfinished capabilities with useful availability explanations and supported next steps.

The MDX components include `Note`, `Button`, `CodeGroup`, `Row`, `Col`, `Properties`, and `Property`. Prefer ordinary Markdown headings, links and tables. Wrap fenced blocks in `CodeGroup`, including standalone commands, following the installed Protocol rendering pattern. Use the repository's `inframeld-documentation` skill for writing guidance.

Use equivalent CLI, cURL, Python, TypeScript and Rust alternatives where implemented. A local CLI version check needs no HTTP alternative. The [version guide](src/app/guides/inspect-cli-version/page.mdx) demonstrates a short human task. The [Project naming guide](src/app/guides/name-and-rename-project/page.mdx) demonstrates a protected write and its generated SDK alternatives. The client pages own complete setup and first-request programs.

## Maintain the API reference

`ApiOperation` and `ApiSchema` in `src/components/ApiReference.tsx` read the committed `contracts/openapi/v1/inframeld-v1.json` directly. Place an `ApiOperation operationId="..."` view beside its explanation in the appropriate API section. The model catalog uses exact schema-name anchors and `ApiSchema name="..."` views. Keep request examples and authorization explanations beside these native shapes rather than maintaining another schema specification or application client.

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

Typecheck generates Next.js route types before running TypeScript, so it works in a fresh checkout without an earlier build. Content checks compile MDX and check local page links, section anchors, public assets, navigation destinations including child links, and delivered operation coverage. They do not fetch external sites or execute SDK examples. Changes to examples need source inspection and relevant client checks as well. Keep execution, visual inspection and unavailable qualification distinct in the handoff.

The `--webpack` flag is required for development and builds: the Protocol search module creates a FlexSearch index through a custom Webpack loader. Theme switching, mobile navigation, section tracking, code tabs, and search remain part of the template. New documentation content is indexed at build time and during development.

When previewing alongside another checkout, choose a separate port with `pnpm --filter @inframeld/docs exec next dev --webpack --port 3091`. Preserve the existing server and stop your own preview when finished. Check installation and existing-user paths, search, code tabs, copy controls and narrow-screen navigation.
