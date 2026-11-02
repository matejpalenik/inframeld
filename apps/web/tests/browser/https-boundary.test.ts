import { test } from "node:test"
import { chromium } from "playwright"
import {
  beginLogin,
  human,
  issuerOrigin,
  nativeFailure,
  nativeInvariant,
  origin,
  passwordLogin,
} from "./support"
import type { NativePhase } from "./support"

test(
  "private-CA browser routing preserves secure host-only cookies and rejects public administration",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({
        channel: "chromium",
        headless: true,
      })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let phase: NativePhase = "browser-version"
    let primary: Error | undefined
    try {
      if (!browser.version().startsWith("156.")) throw nativeInvariant(phase)
      phase = "browser-context"
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      phase = "page-create"
      const page = await context.newPage()
      phase = "login"
      await beginLogin(page)
      await passwordLogin(page, await human())
      phase = "cookie-read"
      const cookies = await context.cookies(origin)
      const sessionCookie = cookies.find(
        (value) => value.name === "ory_kratos_session"
      )
      if (!sessionCookie) throw nativeInvariant("cookie-present")
      if (!sessionCookie.secure) throw nativeInvariant("cookie-secure")
      if (!sessionCookie.httpOnly) throw nativeInvariant("cookie-http-only")
      if (sessionCookie.path !== "/") throw nativeInvariant("cookie-path")
      if (sessionCookie.domain !== "inframeld.account.test")
        throw nativeInvariant("cookie-host-only")
      if (sessionCookie.sameSite !== "Lax")
        throw nativeInvariant("cookie-same-site")
      phase = "cookie-isolation"
      if (
        (await context.cookies(issuerOrigin)).some(
          (value) => value.name === sessionCookie.name
        )
      )
        throw nativeInvariant(phase)
      phase = "public-route"
      for (const [routeIndex, path] of [
        "/admin/identities",
        "/admin/clients",
        "/internal/v1/identity-recovery/admit",
      ].entries()) {
        const response = await page.goto(`${origin}${path}`)
        if (!response || response.status() < 400)
          throw nativeInvariant(phase, {
            routeIndex,
            httpStatus: response?.status(),
          })
      }
      phase = "consent-page"
      const response = await page.goto(
        `${origin}/consent?consent_challenge=unavailable`
      )
      if (!response?.headers()["cache-control"]?.includes("no-store"))
        throw nativeInvariant("cache-header", {
          httpStatus: response?.status(),
        })
      if (response.headers()["referrer-policy"] !== "no-referrer")
        throw nativeInvariant("referrer-header")
      phase = "missing-consent-control"
      if (await page.getByRole("button", { name: "Allow CLI access" }).count())
        throw nativeInvariant(phase)
      phase = "storage"
      const persisted = await page.evaluate(() =>
        [...Object.values(localStorage), ...Object.values(sessionStorage)].join(
          "\n"
        )
      )
      if (
        /ory_|access_token|refresh_token|id_token|code_verifier|unavailable/.test(
          persisted
        )
      )
        throw nativeInvariant(phase)
    } catch (error) {
      primary = nativeFailure(phase, error)
    } finally {
      try {
        await browser.close()
      } catch (error) {
        const close = nativeFailure("browser-close", error)
        if (!primary) throw close
        const combined = new AggregateError(
          [primary, close],
          "Native check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)
