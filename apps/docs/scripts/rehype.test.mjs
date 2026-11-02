import assert from "node:assert/strict"
import { test } from "node:test"

import { compile } from "@mdx-js/mdx"
import { visit } from "unist-util-visit"

async function highlight(code, language = "") {
  const { rehypePlugins } = await import("../src/mdx/rehype.mjs")
  let block

  await compile(`\`\`\`${language}\n${code}\n\`\`\``, {
    rehypePlugins: [
      ...rehypePlugins,
      () => (tree) => {
        visit(tree, "element", (node) => {
          if (node.tagName === "pre") block = node
        })
      },
    ],
  })

  assert.ok(block, "the compiled example retains its code panel")
  return {
    code: block.properties.code,
    html: block.children[0].children[0].value,
  }
}

test("highlights code with the documentation palette and preserves copyable source", async () => {
  const source = 'const message = "<script>alert(1)</script> & text"'
  const result = await highlight(source, "javascript")

  assert.equal(result.code, `${source}\n`)
  assert.match(result.html, /var\(--shiki-token-keyword\)/)
  assert.match(result.html, /var\(--shiki-token-string-expression\)/)
  assert.match(result.html, /(?:&lt;|&#x3C;)script(?:&gt;|>)/)
  assert.match(result.html, /(?:&amp;|&#x26;) text/)
  for (const tag of ["<script", "<pre", "<code"]) {
    assert.equal(result.html.includes(tag), false)
  }
})

test("renders unlabeled and plain-text code safely without nested code panels", async () => {
  for (const language of ["", "text"]) {
    const result = await highlight("<example> & text", language)

    assert.equal(result.code, "<example> & text\n")
    assert.match(
      result.html,
      /(?:&lt;|&#x3C;)example(?:&gt;|>) (?:&amp;|&#x26;) text/
    )
    for (const tag of ["<example", "<pre", "<code"]) {
      assert.equal(result.html.includes(tag), false)
    }
  }
})
