import assert from "node:assert/strict"
import { createHmac, randomBytes } from "node:crypto"
import { readFile } from "node:fs/promises"
import { test } from "node:test"
import { chromium } from "playwright"
import type { BrowserContext, Page, Response } from "playwright"
import {
  beginLogin,
  browserLogout,
  clearMail,
  mailCode,
  nativeFailure,
  nativeInvariant,
  passwordLogin,
  productSession,
  session,
} from "./support"
import type { FixtureHuman, NativePhase } from "./support"

const origin = "https://inframeld.account.test:8443"

function assertAccountPolicy(response: Response | null) {
  assert.equal(
    response?.headers()["content-security-policy"],
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://hydra.account.test:8443 https://login.identity.test:8443"
  )
}

test(
  "native configured OIDC registration uses verified HTTPS metadata and the existing exact identity",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "account-oidc"
    let violations = 0
    let selections = 0
    let authorizations = 0
    try {
      // A separate test site exercises the real cross-site callback cookie path.
      const oidcOrigin = "https://login.identity.test:8443"
      const issuer = `${oidcOrigin}/inframeld`
      const discovery = await fetch(
        `${issuer}/.well-known/openid-configuration`,
        { redirect: "error", signal: AbortSignal.timeout(8_000) }
      )
      assert.equal(discovery.status, 200)
      const metadata: {
        issuer: string
        authorization_endpoint: string
        token_endpoint: string
        jwks_uri: string
      } = await discovery.json()
      assert.equal(metadata.issuer, issuer)
      assert.equal(metadata.authorization_endpoint, `${issuer}/authorize`)
      assert.equal(metadata.token_endpoint, `${issuer}/token`)
      assert.equal(metadata.jwks_uri, `${issuer}/jwks`)
      const keys = await fetch(metadata.jwks_uri, {
        redirect: "error",
        signal: AbortSignal.timeout(8_000),
      })
      assert.equal(keys.status, 200)
      const jwks: { keys: unknown[] } = await keys.json()
      assert.ok(jwks.keys.length > 0)
      const expected: { subject: string } = JSON.parse(
        await readFile("/run/account-fixture/oidc.json", "utf8")
      )
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      await page.exposeFunction("accountOidcFormViolation", () => {
        violations++
      })
      await page.addInitScript(() => {
        document.addEventListener("securitypolicyviolation", (event) => {
          if (event.effectiveDirective === "form-action") {
            const report = Reflect.get(
              window,
              "accountOidcFormViolation"
            ) as () => Promise<void>
            void report()
          }
        })
      })
      page.on("request", (request) => {
        const url = new URL(request.url())
        if (
          url.origin === origin &&
          url.pathname === "/self-service/registration" &&
          request.method() === "POST"
        )
          selections++
        if (
          url.origin === oidcOrigin &&
          url.pathname === "/inframeld/authorize" &&
          request.isNavigationRequest()
        )
          authorizations++
      })
      const response = await page.goto(`${origin}/registration`, {
        waitUntil: "networkidle",
      })
      assertAccountPolicy(response)
      const company = page.getByRole("region", { name: "Company sign-in" })
      const email = company.locator('input[name="traits.email"]')
      assert.equal(await email.inputValue(), "")
      assert.equal(
        await email.evaluate((input: HTMLInputElement) => input.required),
        true
      )
      const csrf = await company
        .locator('input[name="csrf_token"]')
        .inputValue()
      assert.ok(csrf.length > 0)
      const [selection, authorization, callback] = await Promise.all([
        page
          .waitForRequest(
            (request) => {
              const url = new URL(request.url())
              return (
                url.origin === origin &&
                url.pathname === "/self-service/registration" &&
                request.method() === "POST"
              )
            },
            { timeout: 15_000 }
          )
          .catch((error) => {
            throw nativeFailure("oidc-registration-request", error, {
              violations,
              decisions: selections,
              count: authorizations,
            })
          }),
        page
          .waitForRequest(
            (request) => {
              const url = new URL(request.url())
              return (
                url.origin === oidcOrigin &&
                url.pathname === "/inframeld/authorize" &&
                request.isNavigationRequest()
              )
            },
            { timeout: 15_000 }
          )
          .catch((error) => {
            throw nativeFailure("oidc-authorization-request", error, {
              violations,
              decisions: selections,
              count: authorizations,
            })
          }),
        page
          .waitForRequest(
            (request) => {
              const url = new URL(request.url())
              return (
                url.origin === origin &&
                url.pathname ===
                  "/self-service/methods/oidc/callback/company" &&
                request.isNavigationRequest()
              )
            },
            { timeout: 15_000 }
          )
          .catch((error) => {
            throw nativeFailure("oidc-callback-request", error, {
              violations,
              decisions: selections,
              count: authorizations,
            })
          }),
        company
          .locator('button[name="provider"][value="company"]')
          .click()
          .catch((error) => {
            throw nativeFailure("oidc-provider-submit", error, {
              violations,
              decisions: selections,
              count: authorizations,
            })
          }),
      ])
      phase = "oidc-selection-headers"
      const selectionHeaders = await selection.allHeaders()
      phase =
        selectionHeaders.origin === origin
          ? "oidc-origin-expected"
          : selectionHeaders.origin === "null"
            ? "oidc-origin-null"
            : selectionHeaders.origin === undefined
              ? "oidc-origin-absent"
              : "oidc-origin-other"
      // Native form navigation retains the configured no-referrer policy.
      assert.equal(selectionHeaders.origin, "null")
      phase = "oidc-selection-cookie"
      assert.ok(selectionHeaders.cookie?.length)
      phase = "oidc-selection-authorization"
      assert.equal(selectionHeaders.authorization, undefined)
      phase = "oidc-selection-csrf"
      const submitted = new URLSearchParams(selection.postData() ?? "")
      assert.deepEqual(submitted.getAll("csrf_token"), [csrf])
      phase = "oidc-selection-provider"
      assert.deepEqual(submitted.getAll("provider"), ["company"])
      phase = "oidc-authorization-method"
      const authorizationHeaders = await authorization.allHeaders()
      assert.equal(authorization.method(), "GET")
      phase = "oidc-authorization-cookie"
      assert.equal(authorizationHeaders.cookie, undefined)
      phase = "oidc-authorization-credential"
      assert.equal(authorizationHeaders.authorization, undefined)
      phase = "oidc-callback-method"
      assert.equal(callback.method(), "GET")
      phase = "oidc-callback-cookie"
      assert.ok((await callback.allHeaders()).cookie?.length)
      phase = "oidc-navigation-complete"
      await page.waitForLoadState("networkidle")
      phase = "oidc-session-identity"
      const authenticated = await session(context)
      assert.equal(authenticated?.identity?.id, expected.subject)
      phase = "oidc-session-method"
      assert.ok(
        authenticated?.authentication_methods?.some(
          (method) => method.method === "oidc"
        )
      )
      phase = "form-violations"
      assert.equal(violations, 0)
      phase = "decision-count"
      assert.equal(selections, 1)
      assert.equal(authorizations, 1)
      phase = "cookie-read"
      const sessionCookie = (await context.cookies(origin)).find(
        (cookie) => cookie.name === "ory_kratos_session"
      )
      assert.ok(sessionCookie)
      assert.equal(sessionCookie.domain, "inframeld.account.test")
      assert.equal(sessionCookie.path, "/")
      assert.equal(sessionCookie.sameSite, "Lax")
      assert.equal(sessionCookie.secure, true)
      assert.equal(sessionCookie.httpOnly, true)
      assert.equal(
        (await context.cookies(oidcOrigin)).some(
          (cookie) => cookie.name === sessionCookie.name
        ),
        false
      )
      phase = "account-local-state"
      assert.equal((await productSession(context)).response?.status, 403)
    } catch (error) {
      primary = nativeFailure(phase, error, {
        violations,
        decisions: selections,
        count: authorizations,
      })
    } finally {
      try {
        await browser.close()
      } catch (error) {
        const close = nativeFailure("browser-close", error)
        if (!primary) throw close
        const combined = new AggregateError(
          [primary, close],
          "Native OIDC check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)

async function register(
  page: Page,
  context: BrowserContext
): Promise<FixtureHuman> {
  const email = `registered-${randomBytes(12).toString("hex")}@example.test`
  const password = `Native-${randomBytes(24).toString("hex")}!`
  let phase: NativePhase = "registration-open"
  try {
    const response = await page.goto(`${origin}/registration`, {
      waitUntil: "networkidle",
    })
    phase = "registration-policy"
    assertAccountPolicy(response)
    const profile = page.getByRole("region", { name: "Account details" })
    phase = "registration-profile-email"
    await profile.locator('[name="traits.email"]').fill(email)
    phase = "registration-profile-submit"
    await profile.locator('button[name="method"][value="profile"]').click()
    phase = "registration-profile-ready"
    await page.waitForLoadState("networkidle")
    const form = page.getByRole("region", { name: "Set your password" })
    phase = "registration-password-entry"
    await form.locator('[name="password"]').fill(password)
    phase = "registration-password-submit"
    await form.locator('button[name="method"][value="password"]').click()
    phase = "registration-password-ready"
    await page.waitForLoadState("networkidle")
    phase = "registration-session"
    const current = await session(context)
    if (!current?.identity?.id) throw nativeInvariant(phase)
    return { email, password, subject: current.identity.id }
  } catch (error) {
    throw nativeFailure(phase, error)
  }
}

// Produce only a fixture authenticator's RFC6238 code for the native Kratos check.
function authenticatorCode(secret: string): string {
  if (!/^[A-Z2-7]{16,128}$/.test(secret)) throw nativeInvariant("account-mfa")
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
  let bits = ""
  for (const char of secret)
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0")
  const bytes = Buffer.from(
    Array.from({ length: Math.floor(bits.length / 8) }, (_, index) =>
      Number.parseInt(bits.slice(index * 8, index * 8 + 8), 2)
    )
  )
  const counter = Buffer.alloc(8)
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)))
  const digest = createHmac("sha1", bytes).update(counter).digest()
  const offset = digest[digest.length - 1] & 15
  return ((digest.readUInt32BE(offset) & 0x7fff_ffff) % 1_000_000)
    .toString()
    .padStart(6, "0")
}

test(
  "native registration, verification and password settings keep identity separate from admission",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "browser-context"
    try {
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      phase = "account-registration"
      const human = await register(page, context)
      phase = "account-local-state"
      await page
        .getByRole("region", { name: "Current account" })
        .getByText(human.subject, { exact: true })
        .waitFor()
      await page.getByText(/Inframeld access is not available/).waitFor()
      const unadmitted = await productSession(context)
      assert.equal(unadmitted.response?.status, 403)
      assert.equal(unadmitted.data, undefined)

      phase = "verification-mail-clear"
      await clearMail()
      phase = "verification-page-policy"
      assertAccountPolicy(
        await page.goto(`${origin}/verification`, { waitUntil: "networkidle" })
      )
      const verify = page.getByRole("region", { name: "Use an email code" })
      phase = "verification-email-entry"
      await verify.locator('[name="email"]').fill(human.email)
      phase = "verification-code-request"
      await verify.locator('button[name="method"][value="code"]').click()
      phase = "verification-request-ready"
      await page.waitForLoadState("networkidle")
      phase = "verification-mail-code"
      const code = await mailCode(human.email)
      phase = "verification-code-entry"
      await page.locator('input[name="code"]').fill(code)
      phase = "verification-code-submit"
      await page.locator('button[name="method"][value="code"]').click()
      phase = "verification-submit-ready"
      await page
        .getByRole("status")
        .getByText("You successfully verified your email address.", {
          exact: true,
        })
        .waitFor()
      assert.equal(
        await page
          .getByRole("link", { name: "Continue", exact: true })
          .getAttribute("href"),
        `${origin}/`
      )
      assert.equal(
        await page.getByRole("main").locator('form, [role="alert"]').count(),
        0
      )
      phase = "account-local-state"
      const stillUnadmitted = await productSession(context)
      assert.equal(stillUnadmitted.response?.status, 403)
      assert.equal(stillUnadmitted.data, undefined)
      phase = "verification-session"
      const verified = await session(context)
      phase = "verification-identity"
      assert.equal(verified?.identity?.id, human.subject)
      phase = "verification-address"
      assert.ok(
        verified?.identity?.verifiable_addresses?.some(
          (address) => address.verified && address.value === human.email
        )
      )

      phase = "account-settings"
      assertAccountPolicy(
        await page.goto(`${origin}/settings`, { waitUntil: "networkidle" })
      )
      const settings = page.getByRole("region", { name: "Set your password" })
      const replacement = `Replacement-${randomBytes(24).toString("hex")}!`
      await settings.locator('[name="password"]').fill(replacement)
      await settings.locator('button[name="method"][value="password"]').click()
      await page.waitForLoadState("networkidle")
      await page
        .getByText("Your changes have been saved!", { exact: true })
        .waitFor()
      await page
        .getByRole("region", { name: "Set your password" })
        .locator('[name="password"]')
        .waitFor()
      await browserLogout(page)
      await beginLogin(page)
      await passwordLogin(page, { ...human, password: replacement })
      assert.equal((await session(context))?.identity?.id, human.subject)
      phase = "account-local-state"
      assert.equal((await productSession(context)).response?.status, 403)
      // This case observes page policy. The dedicated recovery case owns completion.
      const [recovery] = await Promise.all([
        page.waitForResponse(
          (response) => {
            const url = new URL(response.url())
            return (
              url.origin === origin &&
              url.pathname === "/recovery" &&
              response.request().isNavigationRequest()
            )
          },
          { timeout: 15_000 }
        ),
        page.goto(`${origin}/recovery`, { waitUntil: "networkidle" }),
      ])
      assertAccountPolicy(recovery)
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
          "Native account check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)

test(
  "native configured TOTP and backup codes enroll, reject invalid factors and complete AAL2",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "browser-context"
    try {
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      phase = "account-registration"
      const human = await register(page, context)
      phase = "mfa-settings"
      await page.goto(`${origin}/settings`, { waitUntil: "networkidle" })
      const totp = page.getByRole("region", {
        name: "Authenticator app",
        exact: true,
      })
      phase = "mfa-qr"
      await totp
        .getByRole("img", { name: "Authenticator app QR code" })
        .waitFor()
      phase = "mfa-secret"
      const secret = (
        await totp
          .getByText(
            "This is your authenticator app secret. Use it if you can not scan the QR code.",
            { exact: true }
          )
          .locator("..")
          .locator("p")
          .nth(1)
          .innerText()
      ).trim()
      phase = "mfa-totp-invalid-entry"
      await totp.locator('[name="totp_code"]').fill("invalid-code")
      phase = "mfa-totp-invalid-submit"
      await totp.locator('button[name="method"][value="totp"]').click()
      phase = "mfa-totp-invalid-ready"
      await page.waitForLoadState("networkidle")
      phase = "mfa-totp-invalid-error"
      await page.getByRole("main").getByRole("alert").first().waitFor()
      phase = "mfa-totp-entry"
      await totp.locator('[name="totp_code"]').fill(authenticatorCode(secret))
      phase = "mfa-totp-submit"
      await totp.locator('button[name="method"][value="totp"]').click()
      phase = "mfa-totp-ready"
      await page.waitForLoadState("networkidle")
      phase = "mfa-totp-unlink"
      await page.locator('button[name="totp_unlink"]').waitFor()

      const lookup = page.getByRole("region", {
        name: "Backup recovery codes",
        exact: true,
      })
      phase = "mfa-lookup-generate"
      await lookup.locator('button[name="lookup_secret_regenerate"]').click()
      phase = "mfa-lookup-generated"
      await page.waitForLoadState("networkidle")
      phase = "mfa-lookup-read"
      const codes = (
        await lookup
          .getByText(
            "These are your back up recovery codes. Please keep them in a safe place!",
            { exact: true }
          )
          .locator("..")
          .locator("p")
          .nth(1)
          .innerText()
      ).split(", ")
      assert.equal(codes.length, 12)
      assert.ok(codes.every((code) => /^[a-z0-9]{8}$/.test(code)))
      phase = "mfa-lookup-confirm"
      await lookup.locator('button[name="lookup_secret_confirm"]').click()
      phase = "mfa-lookup-confirmed"
      await page.waitForLoadState("networkidle")
      phase = "mfa-totp-logout"
      await browserLogout(page)
      phase = "mfa-totp-login-open"
      await beginLogin(page)
      phase = "mfa-totp-password"
      await passwordLogin(page, human)
      phase = "mfa-totp-challenge"
      await page.goto(`${origin}/self-service/login/browser?aal=aal2`, {
        waitUntil: "networkidle",
      })
      const challenge = page.getByRole("region", {
        name: "Authenticator app",
        exact: true,
      })
      phase = "mfa-totp-challenge-entry"
      await challenge
        .locator('[name="totp_code"]')
        .fill(authenticatorCode(secret))
      phase = "mfa-totp-challenge-submit"
      await challenge.locator('button[name="method"][value="totp"]').click()
      phase = "mfa-totp-challenge-ready"
      await page.waitForLoadState("networkidle")
      phase = "mfa-totp-aal"
      assert.equal(
        (await session(context))?.authenticator_assurance_level,
        "aal2"
      )
      phase = "mfa-lookup-logout"
      await browserLogout(page)
      phase = "mfa-lookup-login-open"
      await beginLogin(page)
      phase = "mfa-lookup-password"
      await passwordLogin(page, human)
      phase = "mfa-lookup-challenge"
      await page.goto(`${origin}/self-service/login/browser?aal=aal2`, {
        waitUntil: "networkidle",
      })
      const backup = page.getByRole("region", {
        name: "Backup recovery codes",
        exact: true,
      })
      phase = "mfa-lookup-invalid-entry"
      await backup.locator('[name="lookup_secret"]').fill("invalid-code")
      phase = "mfa-lookup-invalid-submit"
      await backup
        .locator('button[name="method"][value="lookup_secret"]')
        .click()
      phase = "mfa-lookup-invalid-ready"
      await page.waitForLoadState("networkidle")
      phase = "mfa-lookup-invalid-error"
      await page.getByRole("main").getByRole("alert").first().waitFor()
      phase = "mfa-lookup-entry"
      await backup.locator('[name="lookup_secret"]').fill(codes[0])
      phase = "mfa-lookup-submit"
      await backup
        .locator('button[name="method"][value="lookup_secret"]')
        .click()
      phase = "mfa-lookup-ready"
      await page.waitForLoadState("networkidle")
      phase = "mfa-lookup-session"
      const completed = await session(context)
      phase = "mfa-lookup-identity"
      assert.equal(completed?.identity?.id, human.subject)
      phase = "mfa-lookup-aal"
      assert.equal(completed?.authenticator_assurance_level, "aal2")
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
          "Native account check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)

test(
  "native configured OIDC settings unlink stale error and relink preserve the same identity",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "oidc-settings-open"
    try {
      const expected: { subject: string } = JSON.parse(
        await readFile("/run/account-fixture/oidc.json", "utf8")
      )
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      await page.goto(`${origin}/registration`, { waitUntil: "networkidle" })
      await page
        .getByRole("region", { name: "Company sign-in" })
        .locator('button[name="provider"][value="company"]')
        .click()
      await page.waitForLoadState("networkidle")
      assert.equal((await session(context))?.identity?.id, expected.subject)
      assertAccountPolicy(
        await page.goto(`${origin}/settings`, { waitUntil: "networkidle" })
      )
      phase = "oidc-settings-password"
      const password = page.getByRole("region", { name: "Set your password" })
      await password
        .locator('input[name="password"]')
        .fill(`OIDC-${randomBytes(24).toString("hex")}!`)
      await password.locator('button[name="method"][value="password"]').click()
      await page.waitForLoadState("networkidle")
      await page
        .getByText("Your changes have been saved!", { exact: true })
        .waitFor()
      const staleUnlink = page
        .getByRole("region", { name: "Company sign-in" })
        .locator('button[name="unlink"][value="company"]')
      await staleUnlink.waitFor()

      const current = await context.newPage()
      assertAccountPolicy(
        await current.goto(`${origin}/settings`, { waitUntil: "networkidle" })
      )
      phase = "oidc-settings-unlink"
      await current
        .getByRole("region", { name: "Company sign-in" })
        .locator('button[name="unlink"][value="company"]')
        .click()
      await current.waitForLoadState("networkidle")
      const company = current.getByRole("region", { name: "Company sign-in" })
      await company.locator('button[name="link"][value="company"]').waitFor()
      assert.equal((await session(context))?.identity?.id, expected.subject)

      // Both buttons came from real native settings flows. The earlier one is now stale.
      phase = "oidc-settings-stale-error"
      await staleUnlink.click()
      await page.waitForLoadState("networkidle")
      await page
        .getByRole("alert")
        .filter({ hasText: /connection|provider|link/i })
        .first()
        .waitFor()
      assert.equal((await session(context))?.identity?.id, expected.subject)

      phase = "oidc-settings-link"
      const csrf = await company
        .locator('input[name="csrf_token"]')
        .inputValue()
      const [submitted] = await Promise.all([
        current
          .waitForRequest(
            (request) =>
              new URL(request.url()).pathname === "/self-service/settings" &&
              request.method() === "POST",
            { timeout: 15_000 }
          )
          .catch((error) => {
            throw nativeFailure("oidc-settings-link", error)
          }),
        company
          .locator('button[name="link"][value="company"]')
          .click()
          .catch((error) => {
            throw nativeFailure("oidc-settings-link", error)
          }),
      ])
      const headers = await submitted.allHeaders()
      assert.equal(headers.origin, "null")
      assert.ok(headers.cookie)
      assert.equal(headers.authorization, undefined)
      const fields = new URLSearchParams(submitted.postData() ?? "")
      assert.deepEqual(fields.getAll("link"), ["company"])
      assert.deepEqual(fields.getAll("csrf_token"), [csrf])
      await current.waitForLoadState("networkidle")
      await current
        .getByRole("region", { name: "Company sign-in" })
        .locator('button[name="unlink"][value="company"]')
        .waitFor()
      phase = "oidc-settings-identity"
      assert.equal((await session(context))?.identity?.id, expected.subject)
      assert.equal((await productSession(context)).response?.status, 403)
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
          "Native OIDC settings check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)
