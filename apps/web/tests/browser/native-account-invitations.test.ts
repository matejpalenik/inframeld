import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { appendFile, readFile } from "node:fs/promises"
import { test } from "node:test"
import {
  createAccessGroup,
  createProject,
  getMyOrganizationAccess,
  getMyProjectAccess,
  issueInvitation,
  revokeInvitation,
} from "@inframeld/sdk"
import type { Browser, BrowserContext, Page } from "playwright"
import { chromium } from "playwright"
import {
  beginLogin,
  browserLogout,
  clearMail,
  human,
  mailCode,
  nativeFailure,
  passwordLogin,
  productClient,
  productSession,
  requestCode,
  session,
  submitCode,
} from "./support"
import type { NativePhase } from "./support"

const origin = "https://inframeld.account.test:8443"
const writeHeaders = { Origin: origin, "X-Inframeld-CSRF": "1" }

async function recipient(context: BrowserContext, page: Page) {
  const fixture: { subject: string; email: string } = JSON.parse(
    await readFile("/run/account-fixture/recipient.json", "utf8")
  )
  await clearMail()
  await beginLogin(page)
  await requestCode(page, fixture.email)
  await submitCode(page, await mailCode(fixture.email))
  assert.equal((await session(context))?.identity?.id, fixture.subject)
  return fixture
}

async function invitation(browser: Browser, mixed: boolean) {
  const context = await browser.newContext({ ignoreHTTPSErrors: false })
  const page = await context.newPage()
  await beginLogin(page)
  await passwordLogin(page, await human())
  const client = await productClient(context)
  const access = await getMyOrganizationAccess({ client })
  assert.equal(access.response?.status, 200)
  assert.ok(access.data)
  let projectId: string | undefined, accessGroupId: string | undefined
  if (mixed) {
    const project = await createProject({
      client,
      headers: { ...writeHeaders, "Idempotency-Key": randomUUID() },
      body: {
        organizationId: access.data.organizationId,
        expectedAccessRevision: access.data.accessRevision,
        name: `account-${randomUUID().replaceAll("-", "")}`,
        displayName: "Account invitation Project",
      },
    })
    assert.equal(project.response?.status, 201)
    assert.ok(project.data)
    projectId = project.data.projectId
    const group = await createAccessGroup({
      client,
      path: { project_id: projectId },
      headers: { ...writeHeaders, "Idempotency-Key": randomUUID() },
      body: {
        expectedAccessRevision: project.data.accessRevision,
        name: "account-invite",
        displayName: "Account invitation group",
      },
    })
    assert.equal(group.response?.status, 201)
    assert.ok(group.data)
    accessGroupId = group.data.accessGroupId
  }
  const current = await getMyOrganizationAccess({ client })
  assert.ok(current.data)
  const project = projectId
    ? await getMyProjectAccess({ client, path: { project_id: projectId } })
    : undefined
  if (projectId) assert.ok(project?.data)
  const issued = await issueInvitation({
    client,
    headers: { ...writeHeaders, "Idempotency-Key": randomUUID() },
    body: {
      organizationId: current.data.organizationId,
      expectedAccessRevision: current.data.accessRevision,
      expectedProjectAccessRevisions:
        projectId && project?.data
          ? [{ projectId, accessRevision: project.data.accessRevision }]
          : [],
      assignments:
        projectId && accessGroupId
          ? [
              { kind: "project-membership", projectId },
              { kind: "group-membership", projectId, accessGroupId },
            ]
          : [{ kind: "admission-only" }],
    },
  })
  assert.equal(issued.response?.status, 201)
  assert.ok(issued.data?.secretAvailable)
  return { issued: issued.data, client, projectId, accessGroupId }
}

async function openInvitation(page: Page, token: string, key: string) {
  const response = await page.goto(`${origin}/invitations`, {
    waitUntil: "networkidle",
  })
  assert.match(
    response?.headers()["content-security-policy"] ?? "",
    /form-action 'self'/
  )
  assert.match(response?.headers()["cache-control"] ?? "", /no-store/)
  assert.equal(new URL(page.url()).search, "")
  await page
    .getByLabel("Protected invitation token", { exact: true })
    .fill(token)
  await page.getByLabel("Original activation key", { exact: true }).fill(key)
  await page.getByRole("checkbox").check()
}

test(
  "native unadmitted recipient explicitly activates mixed access and recovers a lost original response without previewing again",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "invitation-setup"
    try {
      const prepared = await invitation(browser, true)
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      const account = await recipient(context, page)
      assert.equal((await productSession(context)).response?.status, 403)
      const key = randomUUID()
      let previews = 0,
        activations = 0
      page.on("request", (request) => {
        const path = new URL(request.url()).pathname
        if (path === "/v1/invitations/preview") previews++
        if (path === "/v1/invitations/activate") activations++
      })
      phase = "invitation-preview"
      await openInvitation(page, prepared.issued.invitationToken, key)
      await page
        .getByRole("button", { name: "Preview invitation", exact: true })
        .click()
      await page
        .getByRole("region", { name: "Reviewed invitation" })
        .getByText(/Account invitation group/)
        .waitFor()
      assert.equal(activations, 0)
      assert.equal((await productSession(context)).response?.status, 403)

      phase = "invitation-password"
      await page.goto(`${origin}/settings`, { waitUntil: "networkidle" })
      const password = page.getByRole("region", { name: "Set your password" })
      await password
        .locator('input[name="password"]')
        .fill(`Invitation-${randomUUID()}!`)
      await password.locator('button[name="method"][value="password"]').click()
      await page.waitForLoadState("networkidle")
      await page
        .getByText("Your changes have been saved!", { exact: true })
        .waitFor()
      assert.equal((await session(context))?.identity?.id, account.subject)

      await openInvitation(page, prepared.issued.invitationToken, key)
      await page
        .getByRole("button", { name: "Preview invitation", exact: true })
        .click()
      await page.getByRole("region", { name: "Reviewed invitation" }).waitFor()
      let original: Record<string, unknown> | undefined
      let forwardedStatus: number | undefined
      let routeFailure: Error | undefined
      await page.route("**/v1/invitations/activate", async (route) => {
        try {
          const headers = await route.request().allHeaders()
          assert.equal(headers.origin, origin)
          assert.ok(headers.cookie)
          assert.equal(headers.authorization, undefined)
          assert.equal(headers["x-inframeld-csrf"], "1")
          assert.equal(headers["idempotency-key"], key)
          const response = await route.fetch()
          forwardedStatus = response.status()
          original = await response.json()
        } catch (error) {
          routeFailure = nativeFailure("invitation-activation", error)
        } finally {
          await route.abort("failed").catch((error) => {
            const abort = nativeFailure("invitation-activation", error)
            if (routeFailure) {
              const combined = new AggregateError(
                [routeFailure, abort],
                "Native response observation and abort failed."
              )
              combined.stack = combined.message
              routeFailure = combined
            } else routeFailure = abort
          })
        }
      })
      phase = "invitation-activation"
      await page
        .getByRole("button", {
          name: "Activate reviewed invitation",
          exact: true,
        })
        .click()
      await page
        .getByRole("status")
        .filter({ hasText: "outcome is unknown" })
        .waitFor()
      if (routeFailure) {
        primary = routeFailure
        throw routeFailure
      }
      assert.equal(forwardedStatus, 200)
      assert.ok(original)
      assert.equal(activations, 1)
      assert.equal(
        (await productSession(context)).data?.principalId,
        original.principalId
      )
      await page.unroute("**/v1/invitations/activate")
      const priorPreviews = previews
      phase = "invitation-recovery"
      await page
        .getByRole("button", {
          name: "Recover original activation",
          exact: true,
        })
        .click()
      await page
        .getByRole("status")
        .filter({ hasText: "Activation confirmed" })
        .waitFor()
      assert.equal(previews, priorPreviews)
      assert.equal(activations, 2)
      const shown = page.getByRole("region", {
        name: "Original activation receipt",
      })
      await shown
        .getByText(`Local account: ${String(original.principalId)}`, {
          exact: true,
        })
        .waitFor()
      await shown
        .getByText(`Operation: ${String(original.operationId)}`, {
          exact: true,
        })
        .waitFor()
      await appendFile(
        "/run/account-proof/account-results.jsonl",
        JSON.stringify({
          kind: "invitation",
          identityId: account.subject,
          invitationId: prepared.issued.invitationId,
          organizationId: prepared.issued.organizationId,
          principalId: original.principalId,
          operationId: original.operationId,
          requestKey: key,
          projectId: prepared.projectId,
          accessGroupId: prepared.accessGroupId,
          organizationAccessRevision: original.organizationAccessRevision,
          projectAccessRevisions: original.projectAccessRevisions,
          idempotencyExpiresAt: original.idempotencyExpiresAt,
        }) + "\n",
        { mode: 0o600 }
      )
    } catch (error) {
      primary ??= nativeFailure(phase, error)
    } finally {
      try {
        await browser.close()
      } catch (error) {
        const close = nativeFailure("browser-close", error)
        if (!primary) throw close
        const combined = new AggregateError(
          [primary, close],
          "Native invitation check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)

test(
  "native invitation identity switch clears protected context and restored focus performs no write",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "invitation-setup"
    try {
      const prepared = await invitation(browser, false)
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      await recipient(context, page)
      let writes = 0
      let previews = 0
      page.on("request", (request) => {
        if (new URL(request.url()).pathname === "/v1/invitations/activate")
          writes++
        if (new URL(request.url()).pathname === "/v1/invitations/preview")
          previews++
      })
      phase = "invitation-preview"
      await openInvitation(page, prepared.issued.invitationToken, randomUUID())
      await page
        .getByRole("button", { name: "Preview invitation", exact: true })
        .click()
      await page.getByRole("region", { name: "Reviewed invitation" }).waitFor()
      phase = "invitation-switch-page"
      const second = await context.newPage()
      phase = "invitation-switch-focus"
      await second.bringToFront()
      phase = "invitation-switch-logout"
      await browserLogout(second)
      phase = "invitation-switch-fixture"
      const switched = JSON.parse(
        await readFile("/run/account-fixture/switch.json", "utf8")
      )
      phase = "invitation-switch-login-open"
      await beginLogin(second)
      phase = "invitation-switch-login"
      await passwordLogin(second, switched)
      phase = "invitation-switch-session"
      assert.equal((await session(context))?.identity?.id, switched.subject)
      phase = "invitation-switch-return"
      await page.bringToFront()
      await page.evaluate(() => window.dispatchEvent(new Event("focus")))
      phase = "invitation-switch-session"
      await page
        .locator("[data-protected-invitation]")
        .getByText(switched.subject, { exact: true })
        .waitFor()
      phase = "invitation-switch-token"
      assert.equal(
        await page
          .getByLabel("Protected invitation token", { exact: true })
          .inputValue(),
        ""
      )
      phase = "invitation-switch-key"
      assert.equal(
        await page
          .getByLabel("Original activation key", { exact: true })
          .inputValue(),
        ""
      )
      phase = "subject-cleared"
      assert.equal(
        await page
          .getByLabel("Original activation identity", { exact: true })
          .inputValue(),
        ""
      )
      phase = "invitation-switch-preview"
      assert.equal(
        await page.getByRole("region", { name: "Reviewed invitation" }).count(),
        0
      )
      assert.equal(
        await page
          .getByRole("region", { name: "Original activation receipt" })
          .count(),
        0
      )
      assert.equal(
        await page
          .getByRole("button", {
            name: "Activate reviewed invitation",
            exact: true,
          })
          .count(),
        0
      )
      assert.equal(
        await page
          .getByRole("button", {
            name: "Recover original activation",
            exact: true,
          })
          .isDisabled(),
        true
      )
      assert.equal(
        await page
          .getByRole("button", { name: "Preview invitation", exact: true })
          .isDisabled(),
        true
      )
      phase = "invitation-switch-no-write"
      assert.equal(writes, 0)
      assert.equal(previews, 1)
      phase = "invitation-refresh-focus"
      await page
        .getByRole("button", { name: "Check browser identity", exact: true })
        .focus()
      phase = "invitation-refresh-enter"
      await page.keyboard.press("Enter")
      phase = "invitation-refresh-notice"
      await page
        .getByRole("status")
        .filter({ hasText: "Current identity verified" })
        .waitFor()
      phase = "invitation-refresh-no-write"
      assert.equal(writes, 0)
      assert.equal(previews, 1)
      phase = "invitation-switch-outcome"
      await appendFile(
        "/run/account-proof/account-results.jsonl",
        JSON.stringify({
          kind: "unused-invitation",
          invitationId: prepared.issued.invitationId,
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
          "Native identity switch check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)

test(
  "native unavailable invitation renders a safe denial without activating or disclosing its token",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "invitation-setup"
    try {
      const prepared = await invitation(browser, false)
      const current = await getMyOrganizationAccess({ client: prepared.client })
      assert.ok(current.data)
      const revoked = await revokeInvitation({
        client: prepared.client,
        path: { invitation_id: prepared.issued.invitationId },
        headers: { ...writeHeaders, "Idempotency-Key": randomUUID() },
        body: { expectedAccessRevision: current.data.accessRevision },
      })
      assert.equal(revoked.response?.status, 200)
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      await recipient(context, page)
      phase = "invitation-unavailable"
      let activations = 0
      page.on("request", (request) => {
        if (new URL(request.url()).pathname === "/v1/invitations/activate")
          activations++
      })
      await openInvitation(page, prepared.issued.invitationToken, randomUUID())
      await page
        .getByRole("button", { name: "Preview invitation", exact: true })
        .click()
      await page
        .getByRole("status")
        .filter({ hasText: "not available" })
        .waitFor()
      assert.equal(activations, 0)
      assert.ok(
        !(await page.getByRole("status").innerText()).includes(
          prepared.issued.invitationToken
        )
      )
      assert.equal(new URL(page.url()).search, "")
      await appendFile(
        "/run/account-proof/account-results.jsonl",
        JSON.stringify({
          kind: "unused-invitation",
          invitationId: prepared.issued.invitationId,
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
          "Native unavailable invitation check and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)

test(
  "literal browser invitation guide previews activates and directly recovers on the account origin",
  { timeout: 90_000 },
  async () => {
    const browser = await chromium
      .launch({ channel: "chromium", headless: true })
      .catch((error) => {
        throw nativeFailure("browser-launch", error)
      })
    let primary: Error | undefined
    let phase: NativePhase = "invitation-setup"
    try {
      const prepared = await invitation(browser, false)
      const context = await browser.newContext({ ignoreHTTPSErrors: false })
      const page = await context.newPage()
      const account = JSON.parse(
        await readFile("/run/account-fixture/switch.json", "utf8")
      )
      await beginLogin(page)
      await passwordLogin(page, account)
      const bundle = await readFile(
        "tests/fixtures/invitation-guide.iife.js",
        "utf8"
      )
      const key = randomUUID()
      let previews = 0,
        activations = 0
      let original: Record<string, unknown> | undefined
      page.on("request", (request) => {
        const path = new URL(request.url()).pathname
        if (path === "/v1/invitations/preview") previews++
        if (path === "/v1/invitations/activate") activations++
      })
      phase = "invitation-guide"
      for (const mode of ["preview", "activate", "recover"] as const) {
        await page.goto(origin, { waitUntil: "networkidle" })
        const answers = [mode, prepared.issued.invitationToken, key]
        let rejectDialog!: (error: Error) => void
        const dialogFailure = new Promise<never>((_resolve, reject) => {
          rejectDialog = reject
        })
        const dialog = (event: import("playwright").Dialog) => {
          const accepted =
            event.type() === "confirm"
              ? event.accept()
              : event.accept(answers.shift())
          void accepted.catch((error) =>
            rejectDialog(nativeFailure("invitation-guide", error))
          )
        }
        page.on("dialog", dialog)
        const beforePreviews = previews
        const [message] = await Promise.all([
          Promise.race([
            dialogFailure,
            page.waitForEvent("console", {
              timeout: 15_000,
              predicate: async (event) => {
                if (event.type() !== "info" || event.args().length !== 1)
                  return false
                const value: unknown = await event.args()[0].jsonValue()
                return (
                  !!value &&
                  typeof value === "object" &&
                  (mode === "preview"
                    ? "assignments" in value
                    : "operationId" in value)
                )
              },
            }),
          ]),
          page.addScriptTag({ content: bundle }),
        ]).finally(() => page.off("dialog", dialog))
        const value: Record<string, unknown> = await message
          .args()[0]
          .jsonValue()
        assert.equal(value.invitationId, prepared.issued.invitationId)
        assert.ok(
          !JSON.stringify(value).includes(prepared.issued.invitationToken)
        )
        assert.equal((await session(context))?.identity?.id, account.subject)
        if (mode === "preview") assert.equal(activations, 0)
        else {
          assert.equal(value.httpStatus, 200)
          if (mode === "activate") original = value
          else {
            assert.deepEqual(value, original)
            assert.equal(previews, beforePreviews)
          }
        }
      }
      assert.equal(previews, 2)
      assert.equal(activations, 2)
      assert.ok(original)
      await appendFile(
        "/run/account-proof/account-results.jsonl",
        JSON.stringify({
          kind: "invitation",
          identityId: account.subject,
          invitationId: prepared.issued.invitationId,
          organizationId: prepared.issued.organizationId,
          principalId: original.principalId,
          operationId: original.operationId,
          requestKey: key,
          organizationAccessRevision: original.organizationAccessRevision,
          projectAccessRevisions: original.projectAccessRevisions,
          idempotencyExpiresAt: original.idempotencyExpiresAt,
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
          "Literal browser guide and browser cleanup failed."
        )
        combined.stack = combined.message
        throw combined
      }
    }
    if (primary) throw primary
  }
)
