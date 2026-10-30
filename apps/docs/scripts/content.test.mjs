import assert from "node:assert/strict"
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises"
import { tmpdir } from "node:os"
import path from "node:path"
import { test } from "node:test"

import { validateContent } from "./content.mjs"

async function fixture(t, pages) {
  const root = await mkdtemp(path.join(tmpdir(), "inframeld-docs-"))
  t.after(() => rm(root, { recursive: true, force: true }))
  for (const [route, content] of Object.entries(pages)) {
    const file = path.join(root, "src/app", route, "page.mdx")
    await mkdir(path.dirname(file), { recursive: true })
    await writeFile(file, content)
  }
  return root
}

test("reports a Markdown link to a route that does not exist", async (t) => {
  const root = await fixture(t, { "": "# Home\n\n[Missing](/missing)" })
  assert.match((await validateContent(root)).join("\n"), /\/missing.*route/)
})

test("reports broken section anchors in Markdown and MDX links", async (t) => {
  const root = await fixture(t, {
    "": '# Home\n\n[Missing](/guide#missing)\n\n<Button href="/guide#also-missing">Read</Button>',
    guide: "# Guide\n\n## Setup\n\nReady.",
  })
  const errors = await validateContent(root)
  assert.equal(errors.length, 2)
  assert.match(errors.join("\n"), /#missing.*anchor/)
  assert.match(errors.join("\n"), /#also-missing.*anchor/)
})

test("accepts real routes, duplicate heading slugs, reference links and assets", async (t) => {
  const root = await fixture(t, {
    "": '# Home\n\n[Guide][guide]\n\n[guide]: /guide#setup-2\n\n[Source](https://github.com/matejpalenik/inframeld)\n\n<Button href="/guide#setup">Read</Button>\n\n![Logo](/logo.svg)',
    guide: "# Guide\n\n## Setup\n\nFirst.\n\n## Setup\n\nSecond.\n\n[Home](/)",
  })
  await mkdir(path.join(root, "public"), { recursive: true })
  await writeFile(path.join(root, "public/logo.svg"), "<svg/>")
  assert.deepEqual(
    await validateContent(root, [{ links: [{ href: "/guide" }] }]),
    []
  )
})

test("checks navigation destinations even when no page links to them", async (t) => {
  const root = await fixture(t, { "": "# Home" })
  assert.match(
    (await validateContent(root, [{ links: [{ href: "/deleted" }] }])).join(
      "\n"
    ),
    /navigation.*\/deleted.*route/
  )
})

test("reports invalid MDX rather than silently skipping its links", async (t) => {
  const root = await fixture(t, { "": "# Home\n\n<Note>Unclosed" })
  assert.match((await validateContent(root)).join("\n"), /MDX/)
})
