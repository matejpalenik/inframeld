import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { appendFile, readFile } from "node:fs/promises"
import { setTimeout } from "node:timers/promises"
import { test } from "node:test"
import { admitHuman, getMyOrganizationAccess } from "@inframeld/sdk"
import { chromium } from "playwright"
import {
  beginLogin,
  clearMail,
  human,
  mailCode,
  nativeFailure,
  passwordLogin,
  productClient,
  productSession,
  session,
  submitCode,
} from "./support"
import type { FixtureHuman, NativePhase } from "./support"

const origin = "https://inframeld.account.test:8443"
const hooks = "http://recovery-hooks:8082/internal/test/native-recovery"
// This is the existing private fixture forwarder's dedicated test-only credential.
const hookHeaders = {
  "X-Inframeld-Recovery-Key": "inframeld-native-recovery-hook-test-only",
  "Content-Type": "application/json",
}

test(
  "native recovery separates persisted password from blocked access and real worker completion",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "recovery-admission"
    try {
      const fixture: FixtureHuman = JSON.parse(
        await readFile("/run/account-fixture/recovery.json", "utf8")
      )
      const issuer = await browser.newContext({ ignoreHTTPSErrors: false })
      const issuerPage = await issuer.newPage()
      await beginLogin(issuerPage)
      await passwordLogin(issuerPage, await human())
      const client = await productClient(issuer)
      const access = await getMyOrganizationAccess({ client })
      assert.ok(access.data)
      const admitted = await admitHuman({
        client,
        path: { organization_id: access.data.organizationId },
        body: {
          identityId: fixture.subject,
          expectedAccessRevision: access.data.accessRevision,
        },
        headers: {
          Origin: origin,
          "X-Inframeld-CSRF": "1",
          "Idempotency-Key": randomUUID(),
        },
      })
      assert.equal(admitted.response?.status, 201)
      assert.ok(admitted.data)

      const previous = await browser.newContext({ ignoreHTTPSErrors: false })
      const previousPage = await previous.newPage()
      await beginLogin(previousPage)
      await passwordLogin(previousPage, fixture)
      assert.equal((await productSession(previous)).response?.status, 200)
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      const controlled = await fetch(
        `${hooks}/controls/${fixture.subject}/password-saved`,
        {
          method: "PUT",
          headers: hookHeaders,
          body: JSON.stringify({ position: "before", action: "fail" }),
          redirect: "error",
          signal: AbortSignal.timeout(2_000),
        }
      )
      assert.equal(controlled.status, 204)

      phase = "recovery-mail-clear"
      await clearMail()
      phase = "recovery-page"
      await page.goto(`${origin}/recovery`, { waitUntil: "networkidle" })
      const form = page.getByRole("region", { name: "Use an email code" })
      phase = "recovery-email-entry"
      await form.locator('input[name="email"]').fill(fixture.email)
      phase = "recovery-code-request"
      await form.locator('button[name="method"][value="code"]').click()
      phase = "recovery-request-ready"
      await page.waitForLoadState("networkidle")
      phase = "recovery-mail-code"
      const recoveryCode = await mailCode(fixture.email)
      const recoveryFlowId = new URL(page.url()).searchParams.get("flow")
      assert.ok(recoveryFlowId)
      phase = "recovery-code-submit"
      await submitCode(page, recoveryCode)
      phase = "recovery-settings-visible"
      await page.getByRole("region", { name: "Set your password" }).waitFor()
      const settingsFlowId = new URL(page.url()).searchParams.get("flow")
      assert.ok(settingsFlowId)
      phase = "recovery-previous-session"
      assert.equal(await session(previous), null)
      phase = "recovery-session"
      const recovered = await session(context)
      phase = "recovery-identity"
      assert.equal(recovered?.identity?.id, fixture.subject)
      assert.ok(recovered?.id)
      phase = "recovery-blocked-access"
      assert.equal((await productSession(context)).response?.status, 403)

      const first = `Recovered-${randomUUID()}!`
      const settings = page.getByRole("region", { name: "Set your password" })
      phase = "recovery-password-entry"
      await settings.locator('input[name="password"]').fill(first)
      phase = "recovery-password-submit"
      await settings.locator('button[name="method"][value="password"]').click()
      phase = "recovery-password-ready"
      await page.waitForLoadState("networkidle")
      phase = "recovery-hook-observation"
      const observed = await fetch(
        `${hooks}/observations/${fixture.subject}/password-saved`,
        {
          headers: hookHeaders,
          redirect: "error",
          signal: AbortSignal.timeout(2_000),
        }
      )
      phase = "recovery-hook-status"
      assert.equal(observed.status, 200)
      phase = "recovery-hook-body"
      const notification: {
        received: {
          schemaVersion: number
          eventType: string
          identityId: string
          settingsFlowId: string
          sessionId: string
          sourceRecoveryFlowId: string | null
        }[]
        statuses: number[]
      } = await observed.json()
      phase = "recovery-hook-arrivals"
      // The native resilient client can retry the interrupted 503 twice.
      assert.ok(
        notification.received.length >= 1 && notification.received.length <= 3
      )
      phase = "recovery-hook-binding"
      for (const arrival of notification.received)
        assert.deepEqual(arrival, {
          schemaVersion: 2,
          eventType: "password-settings-saved",
          identityId: fixture.subject,
          settingsFlowId,
          sessionId: recovered.id,
          sourceRecoveryFlowId: recoveryFlowId,
        })
      phase = "recovery-hook-forwarding"
      assert.deepEqual(notification.statuses, [])
      phase = "recovery-password-check-context"
      const check = await browser.newContext({ ignoreHTTPSErrors: false })
      const checkPage = await check.newPage()
      phase = "recovery-password-login-open"
      await beginLogin(checkPage)
      phase = "recovery-password-login"
      await passwordLogin(checkPage, { ...fixture, password: first })
      phase = "recovery-password-identity"
      assert.equal((await session(check))?.identity?.id, fixture.subject)
      phase = "recovery-password-blocked"
      assert.equal((await productSession(check)).response?.status, 403)
      phase = "recovery-blocked-page"
      await checkPage.goto(origin, { waitUntil: "networkidle" })
      phase = "recovery-blocked-notice"
      await checkPage.getByText(/Inframeld access is not available/).waitFor()
      phase = "recovery-no-completion-claim"
      assert.equal(
        await checkPage
          .getByText(/cleanup completed|recovery completed|account is ready/i)
          .count(),
        0
      )

      phase = "recovery-control-clear"
      const cleared = await fetch(
        `${hooks}/controls/${fixture.subject}/password-saved`,
        {
          method: "DELETE",
          headers: hookHeaders,
          redirect: "error",
          signal: AbortSignal.timeout(2_000),
        }
      )
      phase = "recovery-control-cleared"
      assert.equal(cleared.status, 204)
      // A fresh official settings flow in this same native recovery session inherits its binding.
      phase = "recovery-associated-settings"
      await page.goto(`${origin}/settings`, { waitUntil: "networkidle" })
      const fresh = page.getByRole("region", { name: "Set your password" })
      const finalPassword = `Recovered-${randomUUID()}!`
      phase = "recovery-associated-password-entry"
      await fresh.locator('input[name="password"]').fill(finalPassword)
      phase = "recovery-associated-password-submit"
      await fresh.locator('button[name="method"][value="password"]').click()
      phase = "recovery-associated-password-ready"
      await page.waitForLoadState("networkidle")

      phase = "recovery-revoked-session"
      const revokedEnd = performance.now() + 15_000
      let oldSession = await session(check)
      while (oldSession !== null && performance.now() < revokedEnd) {
        await setTimeout(200)
        oldSession = await session(check)
      }
      phase = "recovery-revoked-session-assert"
      assert.equal(oldSession, null)
      phase = "recovery-completed-context"
      const completed = await browser.newContext({ ignoreHTTPSErrors: false })
      const completedPage = await completed.newPage()
      phase = "recovery-completed-login-open"
      await beginLogin(completedPage)
      phase = "recovery-completed-login"
      await passwordLogin(completedPage, {
        ...fixture,
        password: finalPassword,
      })
      phase = "recovery-current-access"
      const accessEnd = performance.now() + 15_000
      let current = await productSession(completed)
      while (
        current.response?.status === 403 &&
        performance.now() < accessEnd
      ) {
        await setTimeout(200)
        current = await productSession(completed)
      }
      phase = "recovery-current-access-status"
      assert.equal(current.response?.status, 200)
      phase = "recovery-current-principal"
      assert.equal(current.data?.principalId, admitted.data.principalId)
      phase = "recovery-completed-page"
      await completedPage.goto(origin, { waitUntil: "networkidle" })
      phase = "recovery-completed-notice"
      await completedPage
        .getByText(/local Inframeld account is admitted/)
        .waitFor()
      phase = "recovery-outcome"
      await appendFile(
        "/run/account-proof/account-results.jsonl",
        JSON.stringify({
          kind: "recovery",
          identityId: fixture.subject,
          principalId: admitted.data.principalId,
          interruptedSettingsFlowId: notification.received[0].settingsFlowId,
        }) + "\n",
        { mode: 0o600 }
      )
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
          "Native recovery check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)
