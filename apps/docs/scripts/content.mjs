import { access, readFile } from "node:fs/promises"
import path from "node:path"

import { compile } from "@mdx-js/mdx"
import { slugifyWithCounter } from "@sindresorhus/slugify"
import glob from "fast-glob"
import { toString } from "mdast-util-to-string"
import remarkGfm from "remark-gfm"
import { visit } from "unist-util-visit"

const origin = "https://docs.inframeld.invalid"

function collectPage(page) {
  return () => (tree) => {
    const slugify = slugifyWithCounter()
    const definitions = new Map()
    visit(tree, "definition", (node) =>
      definitions.set(node.identifier, node.url)
    )
    visit(tree, (node) => {
      // The Protocol renderer adds IDs to h2 headings with this same counter.
      if (node.type === "heading" && node.depth === 2) {
        page.anchors.add(slugify(toString(node)))
      }
      if (node.type === "link" || node.type === "image") {
        page.links.push(node.url)
      }
      if (node.type === "linkReference" || node.type === "imageReference") {
        const url = definitions.get(node.identifier)
        if (url) page.links.push(url)
      }
      if (
        node.type === "mdxJsxFlowElement" ||
        node.type === "mdxJsxTextElement"
      ) {
        for (const attribute of node.attributes) {
          if (attribute.type !== "mdxJsxAttribute") continue
          if (
            attribute.name === "href" &&
            typeof attribute.value === "string"
          ) {
            page.links.push(attribute.value)
          }
          if (attribute.name === "id" && typeof attribute.value === "string") {
            page.anchors.add(attribute.value)
          }
        }
      }
    })
  }
}

export async function validateContent(root, navigation = []) {
  const files = await glob("**/page.mdx", { cwd: path.join(root, "src/app") })
  const pages = new Map()
  const errors = []

  for (const file of files.sort()) {
    const route = "/" + file.replace(/(^|\/)page\.mdx$/, "")
    const page = {
      file,
      route: route.replace(/\/$/, "") || "/",
      anchors: new Set(),
      links: [],
    }
    pages.set(page.route, page)
    try {
      await compile(await readFile(path.join(root, "src/app", file), "utf8"), {
        remarkPlugins: [remarkGfm, collectPage(page)],
      })
    } catch (error) {
      errors.push(`${file}: invalid MDX: ${error.message}`)
    }
  }

  const links = [...pages.values()].flatMap((page) =>
    page.links.map((href) => ({ href, source: page.file, route: page.route }))
  )
  for (const group of navigation) {
    for (const link of group.links) {
      links.push({ href: link.href, source: "navigation", route: "/" })
    }
  }

  for (const { href, source, route } of links) {
    let url
    try {
      url = new URL(href, origin + route)
    } catch {
      errors.push(`${source}: ${href} is not a valid URL`)
      continue
    }
    if (url.origin !== origin) continue
    const targetRoute =
      decodeURIComponent(url.pathname).replace(/\/$/, "") || "/"
    const target = pages.get(targetRoute)
    if (!target) {
      const assetPath = path.resolve(root, "public", "." + url.pathname)
      const publicRoot = path.resolve(root, "public") + path.sep
      try {
        if (!assetPath.startsWith(publicRoot)) throw new Error("Outside public")
        await access(assetPath)
      } catch {
        errors.push(`${source}: ${href} has no matching route or public asset`)
      }
      continue
    }
    const anchor = decodeURIComponent(url.hash.slice(1))
    if (anchor && !target.anchors.has(anchor)) {
      errors.push(`${source}: ${href} has no matching section anchor`)
    }
  }
  return errors
}
