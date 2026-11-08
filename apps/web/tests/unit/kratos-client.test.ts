import assert from "node:assert/strict"
import { test } from "node:test"
import { request, Server } from "node:http"
import { once } from "node:events"
import { connect } from "node:net"
import type { NativeDecisionCallback } from "../browser/support"
import { ResponseError } from "@ory/client-fetch"
import { errors } from "playwright"
import { browserLogoutUrl, readLoginFlow } from "../../lib/account/kratos"
import {
  decisionCallback,
  nativeFailure,
  nativeInvariant,
  session,
} from "../browser/support"

const callbackTemplate = new URL(
  "http://127.0.0.1/oauth/callback/" + "a".repeat(64)
)

test("post-listen setup and cleanup failures both survive safe outer classification", async (context) => {
  const secret = "private-setup-cleanup-error"
  const address = Server.prototype.address
  const close = Server.prototype.close
  let port: number | undefined
  context.mock.method(Server.prototype, "address", function (this: Server) {
    const bound = address.call(this)
    if (bound && typeof bound !== "string") port = bound.port
    throw new Error(secret)
  })
  context.mock.method(
    Server.prototype,
    "close",
    function (this: Server, callback?: (error?: Error) => void) {
      return close.call(this, () => callback?.(new Error(secret)))
    }
  )
  const error = await decisionCallback(
    callbackTemplate,
    "expected",
    "allow"
  ).catch((error: unknown) => nativeFailure("decision-route", error))
  assert.ok(port)
  await assert.rejects(callbackRequest(new URL(`http://127.0.0.1:${port}/`)))
  assert.ok(error instanceof AggregateError)
  assert.equal(error.errors.length, 2)
  assert.match(error.errors[0].message, /"phase":"callback-listen"/)
  assert.match(error.errors[1].message, /"phase":"callback-close"/)
  assert.doesNotMatch(
    `${error.message}\n${error.stack}\n${error.errors.map((value) => value.stack).join("\n")}`,
    new RegExp(secret)
  )
})
function callbackRequest(
  url: URL,
  method = "GET",
  host = url.host,
  target?: string
): Promise<{
  status: number
  body: string
  headers: Record<string, string | string[] | undefined>
}> {
  return new Promise((resolve, reject) => {
    const outgoing = request(
      url,
      {
        method,
        headers: { Host: host },
        agent: false,
        signal: AbortSignal.timeout(2_000),
        ...(target === undefined ? {} : { path: target }),
      },
      (response) => {
        let body = ""
        response.on("data", (chunk) => {
          body += String(chunk)
        })
        response.on("end", () =>
          resolve({
            status: response.statusCode ?? 0,
            body,
            headers: response.headers,
          })
        )
      }
    )
    outgoing.on("error", reject)
    outgoing.end()
  })
}

for (const targetKind of ["dot-segment", "network-path", "fragment"] as const) {
  test(`the callback rejects a raw ${targetKind} target before URL normalization`, async () => {
    const callback = await decisionCallback(
      callbackTemplate,
      "expected",
      "allow"
    )
    try {
      const url = new URL(callback.redirectUri)
      const target = `${targetKind === "dot-segment" ? "/other/.." : targetKind === "network-path" ? "//outside.test" : ""}${url.pathname}?state=expected&code=private${targetKind === "fragment" ? "#fragment" : ""}`
      const response = await callbackRequest(url, "GET", url.host, target)
      assert.equal(response.status, 400)
      assert.ok(callback.receipt().failure)
    } finally {
      await callback.close()
    }
  })
}

for (const decision of ["allow", "deny"] as const) {
  test(`the owned callback receives one ${decision} result without reflecting protected parameters`, async () => {
    const secret = "private-callback-state-code"
    const callback = await decisionCallback(callbackTemplate, secret, decision)
    try {
      const url = new URL(callback.redirectUri)
      assert.equal(url.hostname, "127.0.0.1")
      assert.notEqual(url.port, "")
      assert.equal(url.pathname, callbackTemplate.pathname)
      url.search = new URLSearchParams({
        state: secret,
        ...(decision === "allow"
          ? { code: secret }
          : { error: "access_denied" }),
      }).toString()
      const response = await callbackRequest(url)
      assert.equal(response.status, 200)
      assert.match(response.headers["cache-control"] as string, /no-store/)
      assert.equal(response.headers["referrer-policy"], "no-referrer")
      assert.equal(response.headers.connection, "close")
      assert.doesNotMatch(response.body, new RegExp(secret))
      assert.deepEqual(callback.receipt(), { callbacks: 1 })
    } finally {
      await callback.close()
    }
    await assert.rejects(callbackRequest(new URL(callback.redirectUri)))
  })
}

for (const invalid of [
  "state",
  "path",
  "host",
  "method",
  "duplicate-state",
  "contradictory-code",
] as const) {
  test(`the owned callback refuses ${invalid} without admitting a result`, async () => {
    const callback = await decisionCallback(
      callbackTemplate,
      "expected",
      "allow"
    )
    try {
      const url = new URL(callback.redirectUri)
      url.search = "state=expected&code=private"
      if (invalid === "state") url.searchParams.set("state", "wrong")
      if (invalid === "path") url.pathname = "/wrong"
      if (invalid === "duplicate-state")
        url.searchParams.append("state", "expected")
      if (invalid === "contradictory-code")
        url.searchParams.set("error", "access_denied")
      const response = await callbackRequest(
        url,
        invalid === "method" ? "POST" : "GET",
        invalid === "host" ? "outside.test" : url.host
      )
      assert.equal(response.status, 400)
      assert.ok(callback.receipt().failure)
      assert.doesNotMatch(
        JSON.stringify(callback.receipt()),
        /expected|private|outside/
      )
    } finally {
      await callback.close()
    }
    await assert.rejects(callbackRequest(new URL(callback.redirectUri)))
  })
}

test("the callback listener rejects replay after its single terminal response", async () => {
  const callback = await decisionCallback(callbackTemplate, "expected", "allow")
  try {
    const url = new URL(callback.redirectUri)
    url.search = "state=expected&code=private"
    await callbackRequest(url)
    await assert.rejects(callbackRequest(url))
  } finally {
    await callback.close()
  }
})

test("aborting callback ownership closes acceptance and partial sockets", async () => {
  const controller = new AbortController()
  const callback = await decisionCallback(
    callbackTemplate,
    "expected",
    "allow",
    controller.signal
  )
  const url = new URL(callback.redirectUri)
  const socket = connect(Number(url.port), "127.0.0.1")
  socket.on("error", () => {})
  try {
    await once(socket, "connect")
    socket.write("GET /")
    controller.abort()
    await assert.rejects(callbackRequest(url))
    await callback.close()
    assert.equal(socket.destroyed, true)
  } finally {
    socket.destroy()
    await callback.close()
  }
})

test("a pre-aborted callback cannot acquire a listening endpoint", async () => {
  const controller = new AbortController()
  controller.abort()
  let callback: NativeDecisionCallback | undefined
  try {
    await assert.rejects(
      (async () => {
        callback = await decisionCallback(
          callbackTemplate,
          "expected",
          "allow",
          controller.signal
        )
      })()
    )
  } finally {
    await callback?.close()
  }
})

test("the callback closes after assertion failure and permits idempotent finalization", async () => {
  const callback = await decisionCallback(callbackTemplate, "expected", "allow")
  await assert.rejects(
    (async () => {
      try {
        throw new Error("controlled assertion")
      } finally {
        await callback.close()
      }
    })()
  )
  await callback.close()
  await assert.rejects(callbackRequest(new URL(callback.redirectUri)))
})

test(
  "the callback closes an unfinished request within its five-second connection budget",
  { timeout: 8_000 },
  async () => {
    const callback = await decisionCallback(
      callbackTemplate,
      "expected",
      "allow"
    )
    const url = new URL(callback.redirectUri)
    const socket = connect(Number(url.port), "127.0.0.1")
    socket.on("error", () => {})
    try {
      await once(socket, "connect")
      socket.write("GET /")
      await once(socket, "close", { signal: AbortSignal.timeout(6_500) })
      assert.equal(socket.destroyed, true)
    } finally {
      socket.destroy()
      await callback.close()
    }
  }
)

test("the callback admits at most two active sockets and closes all of them", async () => {
  const callback = await decisionCallback(callbackTemplate, "expected", "allow")
  const url = new URL(callback.redirectUri)
  const sockets = []
  try {
    for (let index = 0; index < 3; index += 1) {
      const socket = connect(Number(url.port), "127.0.0.1")
      socket.on("error", () => {})
      sockets.push(socket)
      await once(socket, "connect")
      if (index < 2) socket.write("GET /")
    }
    await once(sockets[2], "close", { signal: AbortSignal.timeout(2_000) })
    assert.equal(sockets[0].destroyed, false)
    assert.equal(sockets[1].destroyed, false)
    await callback.close()
  } finally {
    for (const socket of sockets) socket.destroy()
    await callback.close()
  }
  await assert.rejects(callbackRequest(url))
})

test("eight accepted connections exhaust callback acceptance", async () => {
  const callback = await decisionCallback(callbackTemplate, "expected", "allow")
  const url = new URL(callback.redirectUri)
  try {
    for (let index = 0; index < 8; index += 1) {
      const socket = connect(Number(url.port), "127.0.0.1")
      socket.on("error", () => {})
      try {
        await once(socket, "connect")
      } finally {
        socket.destroy()
      }
      await once(socket, "close")
    }
    await assert.rejects(callbackRequest(url))
  } finally {
    await callback.close()
  }
})

test("the callback refuses upgraded connections without retaining their request", async () => {
  const callback = await decisionCallback(callbackTemplate, "expected", "allow")
  const url = new URL(callback.redirectUri)
  const socket = connect(Number(url.port), "127.0.0.1")
  socket.on("error", () => {})
  try {
    await once(socket, "connect")
    socket.write(
      `GET ${url.pathname}?state=private HTTP/1.1\r\nHost: ${url.host}\r\nConnection: Upgrade\r\nUpgrade: websocket\r\n\r\n`
    )
    await once(socket, "close", { signal: AbortSignal.timeout(2_000) })
    assert.ok(callback.receipt().failure)
    assert.doesNotMatch(JSON.stringify(callback.receipt()), /private|websocket/)
  } finally {
    socket.destroy()
    await callback.close()
  }
})

test("native diagnostics expose typed HTTP facts without retaining protected error data", () => {
  const secret = "diagnostic-private-message-body-url-cookie-token"
  const error = new ResponseError(
    new Response(JSON.stringify({ secret }), { status: 503 }),
    secret
  )
  Object.defineProperty(error, "name", { value: secret })
  Object.defineProperty(error, "cause", { value: { secret }, enumerable: true })
  error.stack = secret
  const result = nativeFailure("consent-inspection", error, { decisions: 1 })
  assert.match(result.message, /"phase":"consent-inspection"/)
  const facts = JSON.parse(result.message)
  assert.equal(facts.kind, "http")
  assert.equal(facts.httpStatus, 503)
  assert.equal(facts.decisions, 1)
  assert.equal(result.cause, undefined)
  assert.doesNotMatch(
    `${result.message}\n${result.stack}\n${JSON.stringify(result)}`,
    new RegExp(secret)
  )
})

for (const phase of [
  "decision-continuation",
  "decision-callback",
  "decision-click",
  "invitation-guide",
  "invitation-activation",
] as const) {
  test(`concurrent ${phase} rejection retains its own origin through an outer catch`, async () => {
    const secret = "diagnostic-private-concurrent-error"
    const operation = Promise.reject(new errors.TimeoutError(secret)).catch(
      (error) => {
        throw nativeFailure(phase, error)
      }
    )
    const waiting = phase.startsWith("invitation-")
      ? Promise.race([operation, new Promise<never>(() => {})])
      : Promise.all([operation, Promise.resolve()])
    const observed = waiting.catch((error) => {
      throw nativeFailure("decision-route", error)
    })
    await assert.rejects(observed, (error: unknown) => {
      assert.ok(error instanceof Error)
      assert.match(error.message, new RegExp(`"phase":"${phase}"`))
      assert.equal(JSON.parse(error.message).kind, "playwright-timeout")
      assert.doesNotMatch(
        `${error.message}\n${error.stack}`,
        new RegExp(secret)
      )
      return true
    })
  })
}

test("unknown errors and invalid counter/status facts remain unknown without payload inspection", () => {
  const secret = "diagnostic-private-unknown-payload"
  const unknown = Object.defineProperty({}, "message", {
    get() {
      throw new Error(secret)
    },
  })
  const result = nativeFailure("cookie-read", unknown)
  assert.match(result.message, /"kind":"unknown"/)
  const invalid = nativeInvariant("recheck-status", {
    httpStatus: 999,
    callbacks: Number.NaN,
    count: -1,
    violations: 101,
    routeIndex: 8,
  })
  const facts = JSON.parse(invalid.message)
  for (const key of [
    "httpStatus",
    "callbacks",
    "count",
    "violations",
    "routeIndex",
  ])
    assert.equal(facts[key], "unknown")
  const untrustedPhase = Reflect.apply(nativeFailure, undefined, [
    secret,
    unknown,
  ])
  assert.ok(untrustedPhase instanceof Error)
  assert.equal(JSON.parse(untrustedPhase.message).phase, "unknown")
  assert.doesNotMatch(
    `${result.message}\n${invalid.message}\n${untrustedPhase.message}`,
    new RegExp(secret)
  )
})

const config = {
  publicOrigin: "https://inframeld.account.test:8443",
  hydraOrigin: "https://hydra.account.test:8443",
  apiInternalUrl: "http://backend:8000",
  kratosInternalUrl: "http://kratos:4433",
  oidcFormActionOrigins: [],
}
const id = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"
const cookie = "ory_kratos_session=current; native_csrf=cookie"
const flow = {
  id,
  type: "browser",
  ui: {
    action: `${config.publicOrigin}/self-service/login?flow=${id}`,
    method: "POST",
    nodes: [],
  },
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

const browser = {
  async cookies() {
    return [
      {
        name: "ory_kratos_session",
        value: "current",
        domain: "inframeld.account.test",
        path: "/",
        expires: -1,
        httpOnly: true,
        secure: true,
        sameSite: "Lax" as const,
      },
    ]
  },
}

test("the native session oracle recognizes an official unauthenticated401", async () => {
  let calls = 0
  const result = await session(browser, async (input, init) => {
    calls += 1
    const request = new Request(input, init)
    assert.equal(new URL(request.url).pathname, "/sessions/whoami")
    assert.equal(request.headers.get("cookie"), "ory_kratos_session=current")
    return json({ error: { id: "session_inactive" } }, 401)
  })
  assert.equal(result, null)
  assert.equal(calls, 1)
})

test("the native session oracle preserves provider503 as failed qualification", async () => {
  await assert.rejects(session(browser, async () => json({}, 503)))
})

for (const [kind, failure] of [
  ["TLS", new TypeError("certificate validation failed")],
  ["transport", new TypeError("connection failed")],
  ["timeout", new DOMException("request deadline", "TimeoutError")],
] as const) {
  test(`the native session oracle preserves ${kind} failure`, async () => {
    await assert.rejects(
      session(browser, async () => {
        throw failure
      })
    )
  })
}

test("reads native browser flow through the official public client with this request's cookie", async () => {
  let seen: Request | undefined
  const result = await readLoginFlow(config, id, cookie, async (url, init) => {
    seen = new Request(url, init)
    return json(flow)
  })
  assert.equal(result.id, id)
  assert.equal(result.type, "browser")
  assert.equal(
    seen?.url,
    `http://kratos:4433/self-service/login/flows?id=${id}`
  )
  assert.equal(seen?.headers.get("Cookie"), cookie)
  assert.equal(seen?.headers.get("Authorization"), null)
  assert.equal(seen?.redirect, "manual")
  assert.equal(seen?.cache, "no-store")
})

test("does not follow provider redirects, oversized bodies or a different/native flow", async () => {
  for (const response of [
    () =>
      new Response(null, {
        status: 302,
        headers: { Location: "https://evil.test/secret" },
      }),
    () => json({ ...flow, type: "api" }),
    () => json({ ...flow, id: "00000000-0000-0000-0000-000000000000" }),
    () => new Response("x".repeat(65_537)),
  ]) {
    let calls = 0
    await assert.rejects(
      readLoginFlow(config, id, cookie, async () => {
        calls++
        return response()
      })
    )
    assert.equal(calls, 1)
  }
})

test("returns only a vetted native browser logout URL without performing logout", async () => {
  const logout = `${config.publicOrigin}/self-service/logout?token=private-native-token`
  let calls = 0
  const result = await browserLogoutUrl(config, cookie, async (url, init) => {
    calls++
    const request = new Request(url, init)
    assert.equal(request.method, "GET")
    assert.equal(new URL(request.url).pathname, "/self-service/logout/browser")
    assert.equal(request.headers.get("Cookie"), cookie)
    return json({ logout_url: logout, logout_token: "private-native-token" })
  })
  assert.equal(result, logout)
  assert.equal(calls, 1)
})

test("never relays an unexpected provider logout target", async () => {
  await assert.rejects(
    browserLogoutUrl(config, cookie, async () =>
      json({
        logout_url: "https://evil.test/self-service/logout?token=private",
        logout_token: "private",
      })
    )
  )
})
