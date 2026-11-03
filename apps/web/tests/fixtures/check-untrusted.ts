import { setTimeout } from "node:timers/promises"
import { chromium } from "playwright"

async function main() {
  const deadline = Date.now() + 60_000
  while (true) {
    try {
      const response = await fetch("https://inframeld.account.test:8443/", {
        signal: AbortSignal.timeout(2_000),
        redirect: "error",
      })
      if (response.status !== 200) throw new Error()
      break
    } catch {
      if (Date.now() >= deadline) throw new Error()
      await setTimeout(200)
    }
  }
  const browser = await chromium.launch({ channel: "chromium", headless: true })
  try {
    if (!browser.version().startsWith("156.")) throw new Error()
    const page = await browser.newPage({ ignoreHTTPSErrors: false })
    let rejected = false
    try {
      await page.goto("https://inframeld.account.test:8443/", {
        timeout: 15_000,
      })
    } catch (error) {
      rejected =
        error instanceof Error &&
        error.message.includes("ERR_CERT_AUTHORITY_INVALID")
    }
    if (!rejected) throw new Error()
  } finally {
    await browser.close()
  }
}
main().catch(() => {
  console.error("Untrusted private-CA browser check failed.")
  process.exitCode = 1
})
