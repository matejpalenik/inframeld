# Make examples useful and verifiable

Alice should be able to tell whether a code block is ready to run or only illustrates one part of an explanation. Name the exact file path and label the block as a complete new file, a replacement, an insertion or a selected teaching fragment. Supply the imports, caller construction and lifecycle needed for a complete example. Do not hide required behavior behind ellipses.

## Connect setup, code and result

Before the example, state the required environment, current credential and retained context. Use environment variables for credentials and clearly recognizable example identifiers. Never include real secrets. For unpublished SDKs, link to the actual local build or installation instructions rather than inventing a registry package.

Give the file path before the code and the execution command after it. Separate shell commands from output. Omit a leading `$` prompt in a copyable command block. Label illustrative output when it was not captured from a controlled run. Explain the meaningful fields immediately after the output.

Language tabs should express the same task with equivalent identifiers, authority, route and expected result. Begin with the smallest useful path and add advanced options later. Use the actual generated client's return types. Python union wrappers, Rust enum variants and TypeScript narrowing differ. Do not replace them with a convenient handwritten application client or an invented shared wrapper.

Show failure handling when it affects safe use. An HTTP 200 response can carry an unresolved observation. Do not convert all non-success product outcomes into transport errors. Keep the delivered JSON shape exactly, including a result such as:

```json
{ "outcome": "unresolved" }
```

This result alone does not establish whether a retained request exists or whether the original action had effects. A comment or surrounding explanation must not claim otherwise. Do not insert a private reason field to make the example easier to explain.

Run copyable examples against controlled fixtures when available. Record whether the example executed, the environment used and the implementation revision. A documentation build proves syntax and supported imports. It does not prove API behavior, persistence, authorization or provider qualification.

## Use the actual Protocol pipeline

Inspect [the component map](../../../../apps/docs/mdx-components.tsx) and [MDX components](../../../../apps/docs/src/components/mdx.tsx) before using a component. The site uses App Router `page.mdx` files with a named `pageMetadata` export. A route's small server `layout.tsx` re-exports that value as Next metadata. Do not export the reserved `metadata` name directly from MDX or assume a YAML frontmatter loader. This adapter avoids an observed SWC pass failure in the installed Next/MDX pipeline. Follow the installed formatter and current build configuration.

This is an illustrative complete page shape for `apps/docs/src/app/example/page.mdx`. It teaches MDX structure and does not establish a product endpoint:

````mdx
export const pageMetadata = {
  title: "Check an original request",
  description:
    "Understand a retained result without submitting the action again.",
};

# Check an original request

Use lookup when you retained the original context but did not receive the response.

## Interpret an unresolved result

```json
{ "outcome": "unresolved" }
```

<Note>
  This result does not establish that the original action had no effects.
</Note>
````

For a new nested route, add its server layout at `apps/docs/src/app/example/layout.tsx`. This is a complete illustrative new file. The root route already has its root layout and must reuse that owner instead of introducing a duplicate. Keep the page's title and description in the one `pageMetadata` object.

```tsx
import type { ReactNode } from "react";

export { pageMetadata as metadata } from "./page.mdx";

export default function Layout({ children }: { children: ReactNode }) {
  return children;
}
```

The code follows the current adapter pattern. Check the neighboring implemented route when adding a page and include the layout in its allocated documentation paths and build verification.

Keep one clear page title. Use useful headings and verify their generated anchors. The current pipeline determines which heading levels enter the page navigation and search index. Preserve existing public anchors when revising a page. Avoid arbitrary imports or client components in ordinary documentation content.

Use `CodeGroup` for equivalent alternatives, such as language versions of one operation. Give each tab an accurate title and keep ordering consistent across pages. A tab must not silently use a different permission model or task. Use the site's copy control and confirm that copied content contains code, not prompts or adjacent output.

Use `Note` for a nearby condition that changes the reader's interpretation. It should not carry the entire happy path. `Row` and `Col` can align a focused explanation with its example when the existing template supports that layout. Keep reading order understandable on a narrow screen. Use `Properties` and `Property` only for an explanatory field subset. Generated schemas remain the authority for exact complete contracts.

MDX treats braces and angle brackets as syntax. Put JSON, shell placeholders and generic type signatures inside code blocks or inline code. Use supported component props rather than relying on unrelated Markdown conventions. Read the actual component implementation if uncertain about slots, titles or children.

## Inspect the rendered result

Check the useful path on a narrow screen and in supported color themes. Confirm headings, internal links, language tabs, copy controls and the page table of contents. Search for the new task and check the destination. An inaccessible warning, clipped code block or copied output can make otherwise accurate instructions unusable.

Keep changes within allocated documentation paths. Shared layout, search and navigation changes need their named owner so concurrent writers do not overwrite one another. Return unresolved rendering or execution gaps in the handoff instead of claiming they passed.
