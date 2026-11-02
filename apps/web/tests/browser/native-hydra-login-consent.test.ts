import { createHash, randomBytes } from "node:crypto"
import { readFile } from "node:fs/promises"
import { test } from "node:test"
import { createClient, inspectHumanOAuthConsent } from "@inframeld/sdk"
import { chromium } from "playwright"
import type { Page } from "playwright"
import {
  browserLogout,
  cookie,
  decisionCallback,
  human,
  issuerOrigin,
  mailCode,
  nativeFailure,
  nativeInvariant,
  origin,
  passwordLogin,
  requestCode,
  session,
  submitCode,
} from "./support"
import type { NativeDecisionCallback, NativePhase } from "./support"

type NavigationFixture = {
  clientId: string
  redirectUri: string
  authorizationEndpoint: string
  issuer: string
  audience: string
}
async function authorizationRequest() {
  const fixture = JSON.parse(
    await readFile("/run/account-fixture/oauth-navigation.json", "utf8")
  ) as NavigationFixture
  const endpoint = new URL(fixture.authorizationEndpoint)
  const callback = new URL(fixture.redirectUri)
  const callbackPath = `/oauth/callback/${createHash("sha256").update(fixture.issuer, "utf8").digest("hex")}`
  if (
    fixture.clientId !== "inframeld-cli" ||
    fixture.issuer !== `${issuerOrigin}/` ||
    fixture.audience !== origin ||
    endpoint.origin !== issuerOrigin ||
    endpoint.pathname !== "/oauth2/auth" ||
    endpoint.search ||
    endpoint.hash ||
    endpoint.username ||
    endpoint.password ||
    callback.protocol !== "http:" ||
    callback.hostname !== "127.0.0.1" ||
    callback.port !== "" ||
    callback.pathname !== callbackPath ||
    fixture.redirectUri !== callback.href ||
    callback.username ||
    callback.password ||
    callback.search ||
    callback.hash
  )
    throw nativeInvariant("fixture")
  // Navigation-only evidence retains no PKCE verifier and performs no exchange.
  const challenge = createHash("sha256")
    .update(randomBytes(48))
    .digest("base64url")
  const state = randomBytes(32).toString("base64url")
  endpoint.search = new URLSearchParams({
    client_id: fixture.clientId,
    redirect_uri: fixture.redirectUri,
    response_type: "code",
    scope: "openid inframeld:api",
    audience: fixture.audience,
    state,
    nonce: randomBytes(32).toString("base64url"),
    code_challenge: challenge,
    code_challenge_method: "S256",
  }).toString()
  return { authorizationUrl: endpoint.href, callback, state }
}

async function reachConsent(
  page: Page,
  method: "password" | "code",
  prepared?: Awaited<ReturnType<typeof authorizationRequest>>
) {
  let phase: NativePhase = "fixture"
  try {
    const attempt = prepared ?? (await authorizationRequest())
    phase = "authorization-navigation"
    await page.goto(attempt.authorizationUrl, { waitUntil: "networkidle" })
    phase = "fixture"
    const fixture = await human()
    phase = "login"
    if (method === "password") await passwordLogin(page, fixture)
    else {
      await requestCode(page, fixture.email)
      await submitCode(page, await mailCode(fixture.email))
    }
    phase = "consent-page"
    await page.waitForURL(
      (url) => url.origin === origin && url.pathname === "/consent",
      { timeout: 15_000 }
    )
    const challenge = new URL(page.url()).searchParams.get("consent_challenge")
    if (!challenge) throw nativeInvariant(phase)
    phase = "consent-inspection"
    const inspected = await inspectHumanOAuthConsent({
      client: createClient({
        baseUrl: origin,
        headers: { Cookie: await cookie(page.context()) },
        cache: "no-store",
        timeoutMs: 8_000,
      }),
      query: { consent_challenge: challenge },
    })
    if (inspected.error)
      throw nativeFailure(phase, inspected.error, {
        httpStatus: inspected.response?.status,
      })
    if (!inspected.data) throw nativeInvariant(phase)
    if (inspected.data.accountSubject !== fixture.subject)
      throw nativeInvariant("consent-subject")
    if (inspected.data.clientId !== "inframeld-cli")
      throw nativeInvariant("consent-client")
    if (inspected.data.installation !== origin)
      throw nativeInvariant("consent-installation")
    phase = "consent-control"
    await page
      .getByRole("button", { name: "Allow CLI access", exact: true })
      .waitFor()
    phase = "consent-visible"
    if (!(await page.getByText(fixture.subject, { exact: true }).isVisible()))
      throw nativeInvariant(phase)
    return { attempt, fixture }
  } catch (error) {
    throw nativeFailure(phase, error)
  }
}

for (const method of ["password", "code"] as const) {
  test(
    `Hydra-initiated ${method} browser login reaches production consent without CSP violations or approval`,
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
      let phase: NativePhase = "browser-context"
      let primary: Error | undefined
      try {
        const context = await browser.newContext({ ignoreHTTPSErrors: false })
        phase = "page-create"
        const page = await context.newPage()
        phase = "display-observation"
        let decisions = 0
        let formViolations = 0
        await page.exposeFunction("accountFormViolation", () => {
          formViolations += 1
        })
        page.on("request", (request) => {
          const url = new URL(request.url())
          if (
            url.origin === origin &&
            url.pathname === "/v1/oauth/consent" &&
            request.method() === "POST"
          )
            decisions += 1
        })
        await page.addInitScript(() => {
          document.addEventListener("securitypolicyviolation", (event) => {
            if (event.effectiveDirective === "form-action") {
              const report = Reflect.get(
                window,
                "accountFormViolation"
              ) as () => Promise<void>
              void report()
            }
          })
        })
        await reachConsent(page, method)
        if (decisions !== 0)
          throw nativeInvariant("decision-count", { decisions })
        if (formViolations !== 0)
          throw nativeInvariant("form-violations", {
            violations: formViolations,
          })
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

  for (const decision of ["allow", "deny"] as const) {
    test(
      `native ${method} login and UI ${decision} reach the registered callback without exchange`,
      { timeout: 90_000 },
      async (test) => {
        const browser = await chromium
          .launch({
            channel: "chromium",
            headless: true,
          })
          .catch((error) => {
            throw nativeFailure("browser-launch", error)
          })
        let phase: NativePhase = "browser-context"
        let primary: Error | undefined
        let callback: NativeDecisionCallback | undefined
        try {
          const context = await browser.newContext({ ignoreHTTPSErrors: false })
          phase = "page-create"
          const page = await context.newPage()
          const prepared = await authorizationRequest()
          callback = await decisionCallback(
            prepared.callback,
            prepared.state,
            decision,
            test.signal
          )
          const authorization = new URL(prepared.authorizationUrl)
          authorization.searchParams.set("redirect_uri", callback.redirectUri)
          const attempt = {
            ...prepared,
            callback: new URL(callback.redirectUri),
            authorizationUrl: authorization.href,
          }
          await reachConsent(page, method, attempt)
          let decisions = 0
          let callbackNavigation = false
          let decisionStatus: number | undefined
          page.on("request", (request) => {
            const url = new URL(request.url())
            if (
              url.origin === attempt.callback.origin &&
              url.pathname === attempt.callback.pathname
            )
              callbackNavigation = request.isNavigationRequest()
            if (
              url.origin === origin &&
              url.pathname === "/v1/oauth/consent" &&
              request.method() === "POST"
            )
              decisions += 1
          })
          page.on("response", (response) => {
            const url = new URL(response.url())
            if (
              url.origin === origin &&
              url.pathname === "/v1/oauth/consent" &&
              response.request().method() === "POST"
            )
              decisionStatus = response.status()
          })
          // The real redirect reaches this process's one-shot loopback receiver.
          phase = "decision-route"
          const continuation = page
            .waitForRequest(
              (request) => {
                const url = new URL(request.url())
                return (
                  request.isNavigationRequest() &&
                  url.origin === issuerOrigin &&
                  url.pathname === "/oauth2/auth"
                )
              },
              { timeout: 15_000 }
            )
            .catch((error) => {
              throw nativeFailure("decision-continuation", error)
            })
          const completed = page
            .waitForURL(
              (url) =>
                url.origin === attempt.callback.origin &&
                url.pathname === attempt.callback.pathname,
              { timeout: 15_000, waitUntil: "domcontentloaded" }
            )
            .catch((error) => {
              throw nativeFailure("decision-callback", error, {
                callbacks: callback?.receipt().callbacks ?? 0,
                decisions,
                httpStatus: decisionStatus ?? Number.NaN,
              })
            })
          await Promise.all([
            continuation,
            completed,
            page
              .getByRole("button", {
                name: decision === "allow" ? "Allow CLI access" : "Cancel",
                exact: true,
              })
              .click()
              .catch((error) => {
                throw nativeFailure("decision-click", error)
              }),
          ])
          const receipt = callback.receipt()
          if (receipt.failure) throw receipt.failure
          if (!callbackNavigation) throw nativeInvariant("callback-navigation")
          if (receipt.callbacks !== 1)
            throw nativeInvariant("callback-count", {
              callbacks: receipt.callbacks,
            })
          if (decisions !== 1)
            throw nativeInvariant("decision-count", { decisions })
        } catch (error) {
          primary = nativeFailure(phase, error)
        } finally {
          const outcomes = await Promise.allSettled([
            Promise.resolve().then(() => browser.close()),
            Promise.resolve().then(() => callback?.close()),
          ])
          const failures = outcomes.flatMap((outcome, index) =>
            outcome.status === "rejected"
              ? [
                  nativeFailure(
                    index === 0 ? "browser-close" : "callback-close",
                    outcome.reason
                  ),
                ]
              : []
          )
          const errors = [...(primary ? [primary] : []), ...failures]
          if (errors.length > 1) {
            const combined = new AggregateError(
              errors,
              "Native check or resource cleanup failed."
            )
            combined.stack = combined.message
            throw combined
          }
          if (errors.length === 1) throw errors[0]
        }
        if (primary) throw primary
      }
    )
  }
}

test(
  "a restored revoked cookie is refused by the current consent recheck without a decision",
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
    let phase: NativePhase = "browser-context"
    let primary: Error | undefined
    try {
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      phase = "page-create"
      const page = await context.newPage()
      const { fixture } = await reachConsent(page, "password")
      phase = "session-active"
      const active = await session(context)
      if (active?.identity?.id !== fixture.subject) throw nativeInvariant(phase)
      phase = "session-cookie"
      const oldCookie = (await context.cookies(origin)).find(
        (value) => value.name === "ory_kratos_session"
      )
      if (!oldCookie) throw nativeInvariant(phase)
      let decisions = 0
      page.on("request", (request) => {
        const url = new URL(request.url())
        if (
          url.origin === origin &&
          url.pathname === "/v1/oauth/consent" &&
          request.method() === "POST"
        )
          decisions += 1
      })
      phase = "logout"
      const logout = await context.newPage()
      await browserLogout(logout)
      await logout.close()
      phase = "restore-cookie"
      await context.addCookies([oldCookie])
      phase = "session-revoked"
      if ((await session(context)) !== null) throw nativeInvariant(phase)
      const checked = page
        .waitForResponse(
          (response) => {
            const url = new URL(response.url())
            return (
              response.request().method() === "GET" &&
              url.origin === origin &&
              url.pathname === "/v1/oauth/consent"
            )
          },
          { timeout: 15_000 }
        )
        .catch((error) => {
          throw nativeFailure("recheck-response", error)
        })
      const [response] = await Promise.all([
        checked,
        (async () => {
          await page.bringToFront()
          await page.evaluate(() => window.dispatchEvent(new Event("focus")))
        })().catch((error) => {
          throw nativeFailure("focus-dispatch", error)
        }),
      ])
      const recheckStatus = response.status()
      if (recheckStatus !== 401)
        throw nativeInvariant("recheck-status", {
          httpStatus: recheckStatus,
        })
      phase = "alert-wait"
      await page
        .getByRole("alert")
        .filter({
          hasText:
            /^Your browser session is unavailable\. Restart sign-in from the requesting client\.$/,
        })
        .waitFor()
        .catch((error) => {
          throw nativeFailure("alert-wait", error, {
            httpStatus: recheckStatus,
          })
        })
      phase = "subject-cleared"
      const subjects = await page
        .getByText(fixture.subject, { exact: true })
        .count()
      if (subjects) throw nativeInvariant(phase, { count: subjects })
      phase = "decision-controls-cleared"
      const controls = await page
        .getByRole("button", { name: "Allow CLI access", exact: true })
        .count()
      if (controls) throw nativeInvariant(phase, { count: controls })
      if (decisions !== 0)
        throw nativeInvariant("decision-count", { decisions })
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
