import { test } from "node:test"
import { setTimeout } from "node:timers/promises"
import { chromium } from "playwright"
import {
  beginLogin,
  browserLogout,
  clearMail,
  human,
  mailCode,
  passwordLogin,
  productSession,
  requestCode,
  session,
  submitCode,
} from "./support"

// Never collect traces, screenshots, console output or raw provider errors from account flows.
test(
  "native password login rejects a wrong password, admits the existing account and explicitly logs out",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium.launch({
      channel: "chromium",
      headless: true,
    })
    try {
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      const fixture = await human()
      await beginLogin(page)
      await passwordLogin(page, fixture, "Incorrect-fixture-password!")
      if (await session(context)) throw new Error()
      if (!(await page.getByRole("main").getByRole("alert").count()))
        throw new Error()
      await passwordLogin(page, fixture)
      if ((await session(context))?.identity?.id !== fixture.subject)
        throw new Error()
      const result = await productSession(context)
      if (!result.data || result.error) throw new Error()
      await page.goto("https://inframeld.account.test:8443/logout")
      if (!(await session(context))) throw new Error()
      await page
        .getByRole("link", { name: "Sign out of browser", exact: true })
        .click()
      await page.waitForLoadState("networkidle")
      if (await session(context)) throw new Error()
    } catch {
      throw new Error(
        "Native password and explicit browser logout qualification failed."
      )
    } finally {
      await browser.close()
    }
  }
)

test(
  "native code login preserves request, wrong code, resend, completion and used-code rejection",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium.launch({
      channel: "chromium",
      headless: true,
    })
    try {
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      const fixture = await human()
      await beginLogin(page)
      await requestCode(page, fixture.email)
      if (await session(context)) throw new Error()
      const first = await mailCode(fixture.email)
      await submitCode(page, first === "000000" ? "111111" : "000000")
      if (await session(context)) throw new Error()
      await clearMail()
      await page.locator('button[name="resend"]').click()
      await page.waitForLoadState("networkidle")
      const code = await mailCode(fixture.email)
      await submitCode(page, code)
      if ((await session(context))?.identity?.id !== fixture.subject)
        throw new Error()
      await browserLogout(page)
      await beginLogin(page)
      await requestCode(page, fixture.email)
      await submitCode(page, code)
      if (await session(context)) throw new Error()
    } catch {
      throw new Error(
        "Native email-code request, resend and completion qualification failed."
      )
    } finally {
      await browser.close()
    }
  }
)

test(
  "native expired code remains unauthenticated",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium.launch({
      channel: "chromium",
      headless: true,
    })
    try {
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      const fixture = await human()
      await beginLogin(page)
      await requestCode(page, fixture.email)
      const code = await mailCode(fixture.email)
      await setTimeout(31_000)
      await submitCode(page, code)
      if (await session(context)) throw new Error()
      if (!(await page.getByRole("main").getByRole("alert").count()))
        throw new Error()
    } catch {
      throw new Error("Native expired-code rejection qualification failed.")
    } finally {
      await browser.close()
    }
  }
)
