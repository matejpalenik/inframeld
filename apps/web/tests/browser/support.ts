import { lstat, readFile } from "node:fs/promises"
import { createServer } from "node:http"
import { createConnection } from "node:net"
import type { Socket } from "node:net"
import { dirname } from "node:path"
import { setTimeout } from "node:timers/promises"
import { Configuration, FrontendApi, ResponseError } from "@ory/client-fetch"
import { createClient, getCurrentSession } from "@inframeld/sdk"
import { errors } from "playwright"
import type { BrowserContext, Page } from "playwright"

const nativePhases = [
  "browser-launch",
  "browser-context",
  "page-create",
  "browser-close",
  "browser-version",
  "fixture",
  "recipient-bridge",
  "recipient-denial",
  "recipient-allow",
  "authorization-navigation",
  "login",
  "consent-page",
  "consent-inspection",
  "consent-subject",
  "consent-client",
  "consent-installation",
  "consent-control",
  "consent-visible",
  "display-observation",
  "form-violations",
  "decision-count",
  "cookie-read",
  "cookie-present",
  "cookie-secure",
  "cookie-http-only",
  "cookie-path",
  "cookie-host-only",
  "cookie-same-site",
  "cookie-isolation",
  "public-route",
  "cache-header",
  "referrer-header",
  "missing-consent-control",
  "storage",
  "decision-route",
  "decision-continuation",
  "decision-callback",
  "decision-click",
  "callback-navigation",
  "callback-method",
  "callback-host",
  "callback-state-shape",
  "callback-state-match",
  "callback-code-shape",
  "callback-no-error",
  "callback-denial-shape",
  "callback-code-absent",
  "callback-count",
  "callback-path",
  "callback-listen",
  "callback-connection",
  "callback-close",
  "session-active",
  "session-cookie",
  "logout",
  "restore-cookie",
  "session-revoked",
  "recheck-response",
  "recheck-status",
  "focus-dispatch",
  "alert-wait",
  "subject-cleared",
  "decision-controls-cleared",
] as const
export type NativePhase = (typeof nativePhases)[number]
type NativeFacts = {
  httpStatus?: number
  decisions?: number
  callbacks?: number
  violations?: number
  count?: number
  routeIndex?: number
}

class NativeCheckFailure extends Error {
  constructor(phase: NativePhase, kind: string, facts: NativeFacts) {
    const bounded = (value: number, minimum: number, maximum: number) =>
      Number.isInteger(value) && value >= minimum && value <= maximum
        ? value
        : "unknown"
    super(
      JSON.stringify({
        phase: nativePhases.includes(phase) ? phase : "unknown",
        kind,
        ...(facts.httpStatus !== undefined && {
          httpStatus: bounded(facts.httpStatus, 100, 599),
        }),
        ...(facts.decisions !== undefined && {
          decisions: bounded(facts.decisions, 0, 100),
        }),
        ...(facts.callbacks !== undefined && {
          callbacks: bounded(facts.callbacks, 0, 100),
        }),
        ...(facts.violations !== undefined && {
          violations: bounded(facts.violations, 0, 100),
        }),
        ...(facts.count !== undefined && {
          count: bounded(facts.count, 0, 100),
        }),
        ...(facts.routeIndex !== undefined && {
          routeIndex: bounded(facts.routeIndex, 0, 2),
        }),
      })
    )
    this.name = "NativeCheckFailure"
    this.stack = `${this.name}: ${this.message}`
  }
}

class NativeCallbackSetupFailure extends AggregateError {
  constructor(primary: Error, cleanup: Error) {
    super([primary, cleanup], "Callback setup and cleanup failed.")
    this.stack = this.message
  }
}

// Native errors can contain flow URLs and cookies. Retain only closed facts.
export function nativeFailure(
  phase: NativePhase,
  error: unknown,
  facts: NativeFacts = {}
): Error {
  if (
    error instanceof NativeCheckFailure ||
    error instanceof NativeCallbackSetupFailure
  )
    return error
  if (error instanceof ResponseError)
    return new NativeCheckFailure(phase, "http", {
      ...facts,
      httpStatus: error.response.status,
    })
  const kind =
    error instanceof errors.TimeoutError
      ? "playwright-timeout"
      : error instanceof TypeError
        ? "type"
        : error instanceof SyntaxError
          ? "syntax"
          : error instanceof DOMException
            ? "dom"
            : error instanceof Error
              ? "error"
              : "unknown"
  return new NativeCheckFailure(phase, kind, facts)
}

export function nativeInvariant(
  phase: NativePhase,
  facts: NativeFacts = {}
): Error {
  return new NativeCheckFailure(phase, "invariant", facts)
}

export type NativeDecisionCallback = {
  redirectUri: string
  receipt(): { callbacks: number; failure?: Error }
  close(): Promise<void>
}

// Own one real browser redirect without exchanging or retaining its code.
export async function decisionCallback(
  registered: URL,
  state: string,
  decision: "allow" | "deny",
  signal?: AbortSignal
): Promise<NativeDecisionCallback> {
  if (signal?.aborted) throw nativeInvariant("callback-listen")
  let callbacks = 0
  let failure: Error | undefined
  let redirectUri = ""
  let consumed = false
  let accepted = 0
  let stopping: Promise<void> | undefined
  let closing: Promise<void> | undefined
  const sockets = new Set<Socket>()
  const server = createServer(
    { maxHeaderSize: 16 * 1024 },
    (request, response) => {
      callbacks += 1
      try {
        if (consumed) throw nativeInvariant("callback-count", { callbacks })
        consumed = true
        if (request.method !== "GET") throw nativeInvariant("callback-method")
        const expected = new URL(redirectUri)
        if (
          request.headers.host !== expected.host ||
          request.rawHeaders.filter(
            (value, index) => index % 2 === 0 && value.toLowerCase() === "host"
          ).length !== 1
        )
          throw nativeInvariant("callback-host")
        if (
          request.headers["content-length"] !== undefined ||
          request.headers["transfer-encoding"] !== undefined
        )
          throw nativeInvariant("callback-method")
        const target = request.url ?? ""
        if (target.split("?")[0] !== expected.pathname || target.includes("#"))
          throw nativeInvariant("callback-path")
        const parameters = new URL(target, expected.origin).searchParams
        if (parameters.getAll("state").length !== 1)
          throw nativeInvariant("callback-state-shape", {
            count: parameters.getAll("state").length,
          })
        if (parameters.get("state") !== state)
          throw nativeInvariant("callback-state-match")
        if (decision === "allow") {
          if (parameters.getAll("code").length !== 1 || !parameters.get("code"))
            throw nativeInvariant("callback-code-shape", {
              count: parameters.getAll("code").length,
            })
          if (parameters.has("error"))
            throw nativeInvariant("callback-no-error")
        } else {
          if (
            parameters.getAll("error").length !== 1 ||
            parameters.get("error") !== "access_denied"
          )
            throw nativeInvariant("callback-denial-shape", {
              count: parameters.getAll("error").length,
            })
          if (parameters.has("code"))
            throw nativeInvariant("callback-code-absent")
        }
      } catch (error) {
        failure ??= nativeFailure("callback-connection", error)
      }
      response.writeHead(failure ? 400 : 200, {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'",
        Connection: "close",
      })
      response.end(
        "<!doctype html><title>Decision navigation completed</title><p>Navigation check completed.</p>"
      )
      void stopAccepting().catch((error) => {
        failure ??= nativeFailure("callback-close", error)
      })
    }
  )
  const stopAccepting = () =>
    (stopping ??= new Promise<void>((resolve, reject) => {
      server.close((error) => {
        if (
          error &&
          !("code" in error && error.code === "ERR_SERVER_NOT_RUNNING")
        )
          reject(nativeFailure("callback-close", error))
        else resolve()
      })
    }))
  const close = () =>
    (closing ??= (async () => {
      signal?.removeEventListener("abort", abort)
      const stopped = stopAccepting()
      const ended = [...sockets].map(
        (socket) =>
          new Promise<void>((resolve) => {
            socket.once("close", () => resolve())
            socket.destroy()
          })
      )
      server.closeAllConnections()
      let timer: ReturnType<typeof globalThis.setTimeout> | undefined
      try {
        await Promise.race([
          Promise.all([stopped, ...ended]),
          new Promise<never>((_, reject) => {
            timer = globalThis.setTimeout(
              () => reject(nativeInvariant("callback-close")),
              5_000
            )
          }),
        ])
      } finally {
        clearTimeout(timer)
      }
    })())
  const abort = () => {
    void close().catch((error) => {
      failure ??= nativeFailure("callback-close", error)
    })
  }
  server.on("connection", (socket) => {
    accepted += 1
    if (sockets.size >= 2) socket.destroy()
    else {
      sockets.add(socket)
      const timer = globalThis.setTimeout(() => {
        failure ??= nativeInvariant("callback-connection")
        socket.destroy()
      }, 5_000)
      socket.on("error", () => {})
      socket.once("close", () => {
        clearTimeout(timer)
        sockets.delete(socket)
      })
    }
    if (accepted === 8)
      void stopAccepting().catch((error) => {
        failure ??= nativeFailure("callback-close", error)
      })
  })
  server.on("upgrade", (_request, socket) => {
    failure ??= nativeInvariant("callback-connection")
    socket.destroy()
  })
  server.on("clientError", (_error, socket) => {
    failure ??= nativeInvariant("callback-connection")
    socket.destroy()
  })
  server.on("error", (error) => {
    failure ??= nativeFailure("callback-listen", error)
  })
  signal?.addEventListener("abort", abort, { once: true })
  try {
    if (signal?.aborted) throw nativeInvariant("callback-listen")
    if (
      registered.protocol !== "http:" ||
      registered.hostname !== "127.0.0.1" ||
      registered.port ||
      registered.username ||
      registered.password ||
      registered.search ||
      registered.hash ||
      !/^\/oauth\/callback\/[a-f0-9]{64}$/.test(registered.pathname)
    )
      throw nativeInvariant("callback-listen")
    await new Promise<void>((resolve, reject) => {
      const ready = () => {
        dispose()
        resolve()
      }
      const failed = () => {
        dispose()
        reject(nativeInvariant("callback-listen"))
      }
      const dispose = () => {
        server.off("listening", ready)
        server.off("error", failed)
        server.off("close", failed)
      }
      server.once("error", failed)
      server.once("close", failed)
      server.once("listening", ready)
      server.listen({ port: 0, host: "127.0.0.1", signal })
    })
    const address = server.address()
    if (
      !address ||
      typeof address === "string" ||
      address.address !== "127.0.0.1" ||
      signal?.aborted
    )
      throw nativeInvariant("callback-listen")
    const redirect = new URL(registered)
    redirect.port = String(address.port)
    redirectUri = redirect.href
    return {
      redirectUri,
      receipt: () => ({ callbacks, ...(failure && { failure }) }),
      close,
    }
  } catch (error) {
    const primary = nativeFailure("callback-listen", error)
    try {
      await close()
    } catch (error) {
      throw new NativeCallbackSetupFailure(
        primary,
        nativeFailure("callback-close", error)
      )
    }
    throw primary
  }
}

export const origin = "https://inframeld.account.test:8443"
export const issuerOrigin = "https://hydra.account.test:8443"

export type RecipientReady = {
  schemaVersion: 1
  type: "authorization-ready"
  authorizationUrl: string
  issuer: string
  callbackUri: string
}

export async function readRecipientBridge(
  path: string,
  deadline: number
): Promise<RecipientReady> {
  const parent = await lstat(dirname(path))
  if (
    !parent.isDirectory() ||
    parent.uid !== process.getuid?.() ||
    (parent.mode & 0o777) !== 0o700
  )
    throw nativeInvariant("recipient-bridge")
  while (true) {
    if (performance.now() >= deadline) throw nativeInvariant("recipient-bridge")
    try {
      const socket = await lstat(path)
      if (
        !socket.isSocket() ||
        socket.uid !== process.getuid?.() ||
        (socket.mode & 0o777) !== 0o600
      )
        throw nativeInvariant("recipient-bridge")
      break
    } catch (error) {
      if (
        !(error instanceof Error) ||
        !("code" in error) ||
        error.code !== "ENOENT"
      )
        throw nativeFailure("recipient-bridge", error)
      await setTimeout(Math.min(25, Math.max(0, deadline - performance.now())))
    }
  }
  return new Promise<RecipientReady>((resolve, reject) => {
    const stream = createConnection(path)
    const readDeadline = Math.min(deadline, performance.now() + 5_000)
    const chunks: Buffer[] = []
    let length = 0
    let finished = false
    let ready: RecipientReady | undefined
    let failure: Error | undefined
    let timer: ReturnType<typeof globalThis.setTimeout>
    const finish = (error?: unknown) => {
      if (finished) return
      finished = true
      failure =
        error === undefined
          ? undefined
          : nativeFailure("recipient-bridge", error)
      stream.destroy()
    }
    const expired = () => {
      if (finished) return
      const remaining = readDeadline - performance.now()
      if (remaining > 0)
        timer = globalThis.setTimeout(expired, Math.ceil(remaining))
      else finish(nativeInvariant("recipient-bridge"))
    }
    timer = globalThis.setTimeout(
      expired,
      Math.max(0, Math.ceil(readDeadline - performance.now()))
    )
    stream.on("data", (chunk: Buffer) => {
      length += chunk.length
      if (length > 128 * 1024) finish(nativeInvariant("recipient-bridge"))
      else chunks.push(chunk)
    })
    stream.once("error", finish)
    stream.once("end", () => {
      if (finished) return
      try {
        if (performance.now() >= readDeadline)
          throw nativeInvariant("recipient-bridge")
        const raw = new TextDecoder("utf-8", { fatal: true }).decode(
          Buffer.concat(chunks)
        )
        const value = JSON.parse(raw) as RecipientReady
        if (
          !raw.endsWith("\n") ||
          !value ||
          typeof value !== "object" ||
          Object.keys(value).sort().join(",") !==
            "authorizationUrl,callbackUri,issuer,schemaVersion,type" ||
          value.schemaVersion !== 1 ||
          value.type !== "authorization-ready" ||
          typeof value.authorizationUrl !== "string" ||
          typeof value.issuer !== "string" ||
          typeof value.callbackUri !== "string"
        )
          throw nativeInvariant("recipient-bridge")
        ready = value
        finish()
      } catch (error) {
        finish(error)
      }
    })
    stream.once("close", () => {
      globalThis.clearTimeout(timer)
      if (failure) reject(failure)
      else if (ready) resolve(ready)
      else reject(nativeInvariant("recipient-bridge"))
    })
  })
}
export type FixtureHuman = { subject: string; email: string; password: string }
export async function human(): Promise<FixtureHuman> {
  return JSON.parse(
    await readFile("/run/account-fixture/human.json", "utf8")
  ) as FixtureHuman
}
export async function cookie(
  context: Pick<BrowserContext, "cookies">
): Promise<string> {
  return (await context.cookies(origin))
    .map((value) => `${value.name}=${value.value}`)
    .join("; ")
}
export async function session(
  context: Pick<BrowserContext, "cookies">,
  transport: typeof globalThis.fetch = globalThis.fetch
) {
  const api = new FrontendApi(
    new Configuration({ basePath: origin, fetchApi: transport })
  )
  try {
    return await api.toSession(
      { cookie: await cookie(context) },
      {
        signal: AbortSignal.timeout(8_000),
        redirect: "error",
        cache: "no-store",
      }
    )
  } catch (error) {
    if (error instanceof ResponseError && error.response.status === 401)
      return null
    throw error
  }
}
export async function productSession(context: BrowserContext) {
  return getCurrentSession({
    client: createClient({
      baseUrl: origin,
      headers: { Cookie: await cookie(context) },
      cache: "no-store",
      timeoutMs: 8_000,
    }),
  })
}
export async function beginLogin(page: Page) {
  await page.goto(`${origin}/login`, { waitUntil: "networkidle" })
  await page.locator('form[action*="/self-service/login"]').first().waitFor()
}
export async function passwordLogin(
  page: Page,
  fixture: FixtureHuman,
  password = fixture.password
) {
  const form = page.getByRole("region", { name: "Use your password" })
  await form.locator('[name="identifier"]').fill(fixture.email)
  await form.locator('[name="password"]').fill(password)
  await form.locator('button[name="method"][value="password"]').click()
  await page.waitForLoadState("networkidle")
}
export async function requestCode(page: Page, email: string) {
  await clearMail()
  const form = page.getByRole("region", { name: "Use an email code" })
  await form.locator('[name="identifier"]').fill(email)
  await form.locator('button[name="method"][value="code"]').click()
  await page.waitForLoadState("networkidle")
  await page.locator('input[name="code"]').waitFor()
}
export async function clearMail() {
  const response = await fetch("http://mailpit:8025/api/v1/messages", {
    method: "DELETE",
    signal: AbortSignal.timeout(2_000),
    redirect: "error",
  })
  if (!response.ok) throw new Error("Disposable mailbox could not be cleared.")
}
export async function mailCode(email: string): Promise<string> {
  const deadline = Date.now() + 15_000
  while (Date.now() < deadline) {
    const response = await fetch("http://mailpit:8025/api/v1/messages", {
      signal: AbortSignal.timeout(2_000),
      redirect: "error",
    })
    const result = (await response.json()) as {
      messages?: { ID: string; To?: { Address: string }[] }[]
    }
    for (const message of result.messages ?? []) {
      if (!message.To?.some((recipient) => recipient.Address === email))
        continue
      const body = await fetch(
        `http://mailpit:8025/api/v1/message/${encodeURIComponent(message.ID)}`,
        { signal: AbortSignal.timeout(2_000), redirect: "error" }
      )
      const content = (await body.json()) as { Text?: string }
      const code = content.Text?.match(/\b[0-9]{6}\b/)?.[0]
      if (code) return code
    }
    await setTimeout(200)
  }
  throw new Error("The native email code did not arrive.")
}
export async function submitCode(page: Page, code: string) {
  const form = page.getByRole("region", { name: "Use an email code" })
  await form.locator('input[name="code"]').fill(code)
  await form
    .locator('button[type="submit"]:not([name="resend"])')
    .first()
    .click()
  await page.waitForLoadState("networkidle")
}
export async function browserLogout(page: Page) {
  await page.goto(`${origin}/logout`)
  await page
    .getByRole("link", { name: "Sign out of browser", exact: true })
    .click()
  await page.waitForLoadState("networkidle")
}
