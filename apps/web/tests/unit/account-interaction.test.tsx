import assert from "node:assert/strict"
import { test } from "node:test"
import { JSDOM } from "jsdom"
import { act } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { AccountState } from "../../components/account/account-state"
import type { AccountView } from "../../lib/account/session"

const origin = "https://inframeld.account.test:8443"
const identity = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"
const principal = "2c447dc1-fd65-4a88-a425-770f6c614897"
const verified: AccountView = {
  kind: "verified",
  identityId: identity,
  access: { kind: "admitted", principalId: principal },
}

for (const [view, text] of [
  [{ kind: "signed-out" }, /No verified browser session/],
  [{ kind: "unavailable" }, /could not be checked/],
  [{ kind: "changed" }, /identity changed/],
] as const) {
  test(`account ${view.kind} is explicit and discloses no old account detail`, () => {
    const html = renderToStaticMarkup(
      <AccountState publicOrigin={origin} initialView={view} />
    )
    assert.match(html, text)
    assert.doesNotMatch(html, new RegExp(`${identity}|${principal}`))
  })
}

test("product403 presentation keeps verified identity separate from unknown admission or restriction", () => {
  const html = renderToStaticMarkup(
    <AccountState
      publicOrigin={origin}
      initialView={{
        kind: "verified",
        identityId: identity,
        access: { kind: "denied" },
      }}
    />
  )
  assert.match(html, new RegExp(identity))
  assert.match(html, /Inframeld access is not available/)
  assert.doesNotMatch(
    html,
    /you are unadmitted|you are suspended|cleanup completed|account is ready/i
  )
})

test("an admitted account still describes action permissions as current checks", () => {
  const html = renderToStaticMarkup(
    <AccountState publicOrigin={origin} initialView={verified} />
  )
  assert.match(html, new RegExp(principal))
  assert.match(html, /current permissions/)
  assert.doesNotMatch(html, /administrator|starter.*ready/i)
})

async function mounted(
  run: (container: HTMLElement, window: JSDOM["window"]) => Promise<void>,
  transport: typeof globalThis.fetch
) {
  const dom = new JSDOM("<!DOCTYPE html><div id='root'></div>", { url: origin })
  const values = {
    window: dom.window,
    document: dom.window.document,
    IS_REACT_ACT_ENVIRONMENT: true,
  }
  const previous = Object.fromEntries(
    Object.keys(values).map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ])
  )
  const oldFetch = globalThis.fetch
  globalThis.fetch = transport
  for (const [key, value] of Object.entries(values))
    Object.defineProperty(globalThis, key, {
      configurable: true,
      value,
      writable: true,
    })
  const { createRoot } = await import("react-dom/client")
  const container = dom.window.document.getElementById("root")!
  const root = createRoot(container)
  try {
    await act(async () =>
      root.render(<AccountState publicOrigin={origin} initialView={verified} />)
    )
    await run(container, dom.window)
  } finally {
    await act(async () => root.unmount())
    dom.window.close()
    globalThis.fetch = oldFetch
    for (const [key, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else Reflect.deleteProperty(globalThis, key)
    }
  }
}

test("account display makes no automatic request on mount or write on restored navigation", async () => {
  let calls = 0
  await mounted(
    async (container, window) => {
      assert.match(container.textContent ?? "", new RegExp(identity))
      assert.equal(calls, 0)
      await act(async () =>
        window.dispatchEvent(
          new window.PageTransitionEvent("pageshow", { persisted: true })
        )
      )
      assert.doesNotMatch(
        container.textContent ?? "",
        new RegExp(`${identity}|${principal}`)
      )
      assert.match(container.textContent ?? "", /No verified browser session/)
      assert.equal(calls, 1)
    },
    async (input, init) => {
      const request = new Request(input, init)
      assert.equal(request.method, "GET")
      assert.equal(request.headers.get("Cookie"), null)
      assert.equal(request.headers.get("Authorization"), null)
      calls++
      return Response.json({}, { status: 401 })
    }
  )
})

test("blur removes protected detail and a late observation cannot restore it", async () => {
  let complete: (response: Response) => void = () => {
    throw new Error("Observation did not start")
  }
  let calls = 0
  await mounted(
    async (container, window) => {
      assert.match(container.textContent ?? "", new RegExp(identity))
      await act(async () => window.dispatchEvent(new window.Event("focus")))
      await act(async () => window.dispatchEvent(new window.Event("blur")))
      assert.doesNotMatch(
        container.textContent ?? "",
        new RegExp(`${identity}|${principal}`)
      )
      await act(async () =>
        complete(
          Response.json({
            active: true,
            identity: { id: identity, state: "active" },
          })
        )
      )
      assert.doesNotMatch(
        container.textContent ?? "",
        new RegExp(`${identity}|${principal}`)
      )
      assert.equal(calls, 1)
    },
    async () => {
      calls++
      return new Promise<Response>((resolve) => {
        complete = resolve
      })
    }
  )
})

test("an explicit account recheck is a single read and replaces stale detail", async () => {
  let calls = 0
  await mounted(
    async (container, window) => {
      const button = container.querySelector("button")
      assert.ok(button)
      await act(async () =>
        button.dispatchEvent(new window.MouseEvent("click", { bubbles: true }))
      )
      assert.equal(calls, 1)
      assert.match(container.textContent ?? "", /No verified browser session/)
      assert.doesNotMatch(
        container.textContent ?? "",
        new RegExp(`${identity}|${principal}`)
      )
    },
    async (input, init) => {
      const request = new Request(input, init)
      assert.equal(request.method, "GET")
      calls++
      return Response.json({}, { status: 401 })
    }
  )
})
