import { readFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"

import { validateContent } from "./content.mjs"

const root = fileURLToPath(new URL("../", import.meta.url))
const navigation = JSON.parse(
  await readFile(new URL("../src/lib/navigation.json", import.meta.url), "utf8")
)
const errors = await validateContent(root, navigation)
if (errors.length) {
  console.error(errors.join("\n"))
  process.exitCode = 1
} else {
  console.log("Documentation MDX, local links and navigation are valid.")
}
