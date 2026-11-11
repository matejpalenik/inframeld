import { createHash } from "node:crypto"
import {
  mkdir,
  readFile,
  stat,
  writeFile,
  unlink,
  rmdir,
} from "node:fs/promises"
import { setTimeout } from "node:timers/promises"
import { test } from "node:test"
import { chromium } from "playwright"
import type { BrowserContext, Page } from "playwright"
import {
  beginLogin,
  passwordLogin,
  productSession,
  session,
  human,
  readRecipientBridge,
  nativeFailure,
  nativeInvariant,
  origin,
  issuerOrigin,
} from "./support"
import type { FixtureHuman } from "./support"

// All cases use the real registered client and existing protected Rust bridge.
// No token, callback code, cookie, trace, screenshot or provider body is logged.
async function claim(
  page: Page,
  context: BrowserContext,
  person: FixtureHuman,
  stage: string
) {
  const parent = `/run/account-proof/bootstrap-${stage}`
  const marker = `/run/account-proof/bootstrap-${stage}-ready`
  const verified = `/run/account-proof/bootstrap-${stage}-verified`
  await mkdir(parent, { mode: 0o700 })
  let primary: unknown
  let marked = false
  try {
    await writeFile(marker, "READY1\n", { flag: "wx", mode: 0o600 })
    marked = true
    const event = await readRecipientBridge(
      `${parent}/browser.sock`,
      performance.now() + 30_000
    )
    const authorization = new URL(event.authorizationUrl)
    const callback = new URL(event.callbackUri)
    const digest = createHash("sha256")
      .update(event.issuer, "utf8")
      .digest("hex")
    if (
      event.issuer !== `${issuerOrigin}/` ||
      authorization.origin !== issuerOrigin ||
      authorization.pathname !== "/oauth2/auth" ||
      authorization.searchParams.get("client_id") !== "inframeld-cli" ||
      authorization.searchParams.get("code_challenge_method") !== "S256" ||
      authorization.searchParams.get("redirect_uri") !== event.callbackUri ||
      callback.protocol !== "http:" ||
      callback.hostname !== "127.0.0.1" ||
      !callback.port ||
      callback.pathname !== `/oauth/callback/${digest}` ||
      callback.search ||
      callback.hash ||
      callback.username ||
      callback.password
    )
      throw nativeInvariant("recipient-bridge")
    await page.goto(event.authorizationUrl, { waitUntil: "networkidle" })
    if (new URL(page.url()).pathname === "/login")
      await passwordLogin(page, person)
    await page.waitForURL(
      (url) => url.origin === origin && url.pathname === "/consent",
      { timeout: 15_000 }
    )
    if ((await session(context))?.identity?.id !== person.subject)
      throw nativeInvariant("consent-subject")
    const received = page.waitForResponse(
      (response) =>
        new URL(response.url()).origin === callback.origin &&
        new URL(response.url()).pathname === callback.pathname &&
        response.request().isNavigationRequest(),
      { timeout: 15_000 }
    )
    const decided = page.waitForResponse(
      (response) =>
        new URL(response.url()).origin === origin &&
        new URL(response.url()).pathname === "/v1/oauth/consent" &&
        response.request().method() === "POST",
      { timeout: 15_000 }
    )
    const [callbackResponse, decisionResponse] = await Promise.all([
      received,
      decided,
      page
        .getByRole("button", { name: "Allow CLI access", exact: true })
        .click(),
    ])
    if (callbackResponse.status() !== 200 || decisionResponse.status() !== 200)
      throw nativeInvariant("recipient-allow")
    const deadline = performance.now() + 30_000
    while (true) {
      try {
        const observed = await stat(verified)
        if (!observed.isFile() || (observed.mode & 0o777) !== 0o600)
          throw nativeInvariant("recipient-bridge")
        break
      } catch (error) {
        if (
          !(error instanceof Error) ||
          !("code" in error) ||
          error.code !== "ENOENT"
        )
          throw error
      }
      if (performance.now() >= deadline)
        throw nativeInvariant("recipient-bridge")
      await setTimeout(25)
    }
    await unlink(verified)
  } catch (error) {
    primary = error
  }
  const cleanup: unknown[] = []
  if (marked) {
    try {
      await unlink(marker)
    } catch (error) {
      cleanup.push(error)
    }
  }
  try {
    await rmdir(parent)
  } catch (error) {
    cleanup.push(error)
  }
  if (cleanup.length)
    throw new AggregateError(
      [...(primary ? [primary] : []), ...cleanup],
      "Bootstrap proof or owned bridge cleanup failed."
    )
  if (primary) throw primary
}

for (const scenario of ["first", "replay", "competing"] as const) {
  test(
    `bootstrap-proof ${scenario} uses official identity and independent installed-consumer effects`,
    { timeout: 90_000 },
    async () => {
      const browser = await chromium.launch({
        channel: "chromium",
        headless: true,
      })
      let primary: unknown
      try {
        if (!browser.version().startsWith("156."))
          throw nativeInvariant("browser-version")
        const context = await browser.newContext({ ignoreHTTPSErrors: false })
        const page = await context.newPage()
        const person =
          scenario === "competing"
            ? (JSON.parse(
                await readFile("/run/account-fixture/switch.json", "utf8")
              ) as FixtureHuman)
            : await human()
        await beginLogin(page)
        await passwordLogin(page, person)
        if ((await session(context))?.identity?.id !== person.subject)
          throw nativeInvariant("consent-subject")
        if (scenario === "first") {
          const before = await productSession(context)
          if (before.response?.status !== 403 || !before.error)
            throw nativeInvariant("account-local-state")
        }
        await claim(page, context, person, scenario)
        if (scenario === "competing")
          await claim(page, context, person, "reused")
        else {
          const after = await productSession(context)
          if (!after.data || after.error)
            throw nativeInvariant("account-local-state")
        }
      } catch (error) {
        primary = nativeFailure("recipient-allow", error)
      }
      try {
        await browser.close()
      } catch (error) {
        throw new AggregateError(
          [
            ...(primary ? [primary] : []),
            nativeFailure("browser-close", error),
          ],
          "Bootstrap or browser cleanup failed."
        )
      }
      if (primary) throw primary
    }
  )
}
