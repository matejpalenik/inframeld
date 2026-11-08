import assert from "node:assert/strict"
import { test } from "node:test"
import { JSDOM } from "jsdom"
import { act } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { InvitationForm } from "../../components/account/invitation-form"

const origin = "https://inframeld.account.test:8443"
const identity = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"
const other = "499abfc3-6a30-4674-82c2-edc58d8962e4"
const invitationId = "2c447dc1-fd65-4a88-a425-770f6c614897"
const organizationId = "210b369f-e208-484d-9a0b-2c2c5409ba24"
const token = "a".repeat(43)
const key = "saved-original-key"
const preview = {
  invitationId,
  organizationId,
  assignments: [{ kind: "admission-only" }],
  scopes: [
    {
      target: { kind: "organization", organizationId },
      displayName: "Support",
    },
  ],
  expiresAt: "2026-11-09T12:00:00Z",
}
const receipt = {
  invitationId,
  organizationId,
  principalId: other,
  operationId: key,
  organizationAccessRevision: 3,
  projectAccessRevisions: [],
  idempotencyExpiresAt: "2026-11-09T12:00:00Z",
}
const session = (id = identity) =>
  Response.json({ active: true, identity: { id, state: "active" } })

async function mounted(
  run: (container: HTMLElement, window: JSDOM["window"]) => Promise<void>,
  transport: typeof globalThis.fetch
) {
  const dom = new JSDOM("<!DOCTYPE html><div id='root'></div>", {
    url: origin,
    pretendToBeVisual: true,
  })
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
    await act(async () => root.render(<InvitationForm publicOrigin={origin} />))
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

async function fill(
  container: HTMLElement,
  window: JSDOM["window"],
  label: string,
  value: string
) {
  const input = container.querySelector<HTMLInputElement>(
    `input[aria-label='${label}']`
  )
  assert.ok(input, `Missing ${label} control`)
  await act(async () => {
    Object.getOwnPropertyDescriptor(
      window.HTMLInputElement.prototype,
      "value"
    )!.set!.call(input, value)
    input.dispatchEvent(new window.Event("input", { bubbles: true }))
  })
}

async function click(
  container: HTMLElement,
  window: JSDOM["window"],
  text: string
) {
  const button = [
    ...container.querySelectorAll<HTMLButtonElement>("button"),
  ].find((item) => item.textContent === text)
  assert.ok(button, `Missing ${text} action`)
  assert.equal(button.disabled, false, `${text} should be available`)
  await act(async () =>
    button.dispatchEvent(new window.MouseEvent("click", { bubbles: true }))
  )
}

async function context(container: HTMLElement, window: JSDOM["window"]) {
  await fill(container, window, "Protected invitation token", token)
  await fill(container, window, "Original activation key", key)
  await fill(container, window, "Original activation identity", identity)
  const saved = container.querySelector<HTMLInputElement>(
    "input[type='checkbox']"
  )
  assert.ok(saved)
  await act(async () =>
    saved.dispatchEvent(new window.MouseEvent("click", { bubbles: true }))
  )
}

test("invitation controls identify installation, protected input and explicit original recovery", () => {
  const html = renderToStaticMarkup(<InvitationForm publicOrigin={origin} />)
  assert.match(html, /Installation:/)
  assert.match(html, /Protected invitation token/)
  assert.match(html, /type="password"/)
  const document = new JSDOM(html).window.document
  assert.equal(
    document.querySelector("input")?.getAttribute("autocomplete"),
    "off"
  )
  assert.match(html, /Recover original activation/)
  assert.match(html, /saved.*token.*key/i)
  assert.doesNotMatch(html, /localStorage|sessionStorage/)
})

test("mount and restored navigation never activate or preview automatically", async () => {
  const methods: string[] = []
  await mounted(
    async (container, window) => {
      assert.match(container.textContent ?? "", /Preview invitation/)
      assert.deepEqual(methods, [])
      await act(async () =>
        window.dispatchEvent(
          new window.PageTransitionEvent("pageshow", { persisted: true })
        )
      )
      assert.deepEqual(methods, ["GET"])
      assert.match(container.textContent ?? "", new RegExp(identity))
    },
    async (input, init) => {
      methods.push(new Request(input, init).method)
      return session()
    }
  )
})

test("preview shows the exact safe scope and requires a separate explicit activation", async () => {
  const paths: string[] = []
  await mounted(
    async (container, window) => {
      await context(container, window)
      await click(container, window, "Preview invitation")
      assert.match(container.textContent ?? "", /Support/)
      assert.match(container.textContent ?? "", /admission-only/)
      assert.equal(paths.filter((path) => path.endsWith("activate")).length, 0)
      await click(container, window, "Activate reviewed invitation")
      assert.equal(paths.filter((path) => path.endsWith("activate")).length, 1)
      assert.match(container.textContent ?? "", /Activation confirmed/)
      assert.match(container.textContent ?? "", new RegExp(other))
    },
    async (input, init) => {
      const path = new URL(new Request(input, init).url).pathname
      paths.push(path)
      return path.endsWith("whoami")
        ? session()
        : Response.json(path.endsWith("preview") ? preview : receipt)
    }
  )
})

test("manual original restoration recovers directly without consumed-token preview", async () => {
  const paths: string[] = []
  await mounted(
    async (container, window) => {
      await context(container, window)
      await click(container, window, "Recover original activation")
      assert.equal(paths.filter((path) => path.endsWith("activate")).length, 1)
      assert.ok(!paths.some((path) => path.endsWith("preview")))
      assert.match(container.textContent ?? "", /Activation confirmed/)
    },
    async (input, init) => {
      const request = new Request(input, init)
      const path = new URL(request.url).pathname
      paths.push(path)
      if (request.method === "GET") return session()
      assert.equal(request.headers.get("Idempotency-Key"), key)
      assert.deepEqual(await request.json(), { invitationToken: token })
      return Response.json(receipt)
    }
  )
})

test("blur hides protected scope and focus changes identity with no automatic write", async () => {
  let changed = false
  let writes = 0
  let reads = 0
  await mounted(
    async (container, window) => {
      await context(container, window)
      await click(container, window, "Preview invitation")
      const region = container.querySelector<HTMLElement>(
        "[data-protected-invitation]"
      )!
      assert.ok(region)
      await act(async () => window.dispatchEvent(new window.Event("blur")))
      assert.equal(region.hidden, true)
      changed = true
      for (let recheck = 0; recheck < 2; recheck++) {
        const previousReads = reads
        await act(async () => window.dispatchEvent(new window.Event("focus")))
        assert.equal(reads, previousReads + 1)
        assert.equal(writes, 1)
        assert.match(container.textContent ?? "", new RegExp(other))
        assert.doesNotMatch(container.textContent ?? "", /Support/)
        for (const label of [
          "Protected invitation token",
          "Original activation key",
          "Original activation identity",
        ])
          assert.equal(
            container.querySelector<HTMLInputElement>(
              `input[aria-label='${label}']`
            )?.value,
            ""
          )
        assert.equal(
          container.querySelector("[aria-label='Reviewed invitation']"),
          null
        )
        assert.equal(
          container.querySelector("[aria-label='Original activation receipt']"),
          null
        )
        const buttons = [
          ...container.querySelectorAll<HTMLButtonElement>("button"),
        ]
        assert.equal(
          buttons.some(
            (button) => button.textContent === "Activate reviewed invitation"
          ),
          false
        )
        for (const name of [
          "Preview invitation",
          "Recover original activation",
        ])
          assert.equal(
            buttons.find((button) => button.textContent === name)?.disabled,
            true
          )
      }
    },
    async (input, init) => {
      const request = new Request(input, init)
      if (request.method === "GET") {
        reads++
        return session(changed ? other : identity)
      }
      writes++
      return Response.json(preview)
    }
  )
})

test("restoring an original under a different verified identity never sends activation", async () => {
  let writes = 0
  await mounted(
    async (container, window) => {
      await context(container, window)
      await click(container, window, "Recover original activation")
      assert.equal(writes, 0)
      assert.match(container.textContent ?? "", /identity changed/i)
      assert.equal(
        container.querySelector<HTMLInputElement>(
          "input[aria-label='Protected invitation token']"
        )?.value,
        ""
      )
    },
    async (input, init) => {
      if (new Request(input, init).method === "GET") return session(other)
      writes++
      return Response.json(receipt)
    }
  )
})

test("lost response preserves the original for explicit recovery but focus never resubmits", async () => {
  let writes = 0
  let identityUnavailable = false
  const bodies: unknown[] = []
  await mounted(
    async (container, window) => {
      await context(container, window)
      await click(container, window, "Recover original activation")
      assert.match(container.textContent ?? "", /outcome is unknown/)
      identityUnavailable = true
      await act(async () => window.dispatchEvent(new window.Event("blur")))
      await act(async () => window.dispatchEvent(new window.Event("focus")))
      assert.equal(writes, 1)
      assert.match(container.textContent ?? "", /outcome is unknown/)
      identityUnavailable = false
      await act(async () => window.dispatchEvent(new window.Event("focus")))
      assert.equal(writes, 1)
      await click(container, window, "Recover original activation")
      assert.equal(writes, 2)
      assert.deepEqual(bodies, [
        { invitationToken: token },
        { invitationToken: token },
      ])
      assert.match(container.textContent ?? "", /Activation confirmed/)
      await click(container, window, "Discard protected context")
      assert.equal(
        container.querySelector<HTMLInputElement>(
          "input[aria-label='Protected invitation token']"
        )?.value,
        ""
      )
      assert.doesNotMatch(container.textContent ?? "", new RegExp(other))
    },
    async (input, init) => {
      const request = new Request(input, init)
      if (request.method === "GET")
        return identityUnavailable
          ? Response.json({}, { status: 503 })
          : session()
      writes++
      bodies.push(await request.json())
      assert.equal(request.headers.get("Idempotency-Key"), key)
      if (writes === 1) throw new Error("Lost response")
      return Response.json(receipt)
    }
  )
})

test("cancel waiting retains uncertainty and late completion cannot restore protected detail", async () => {
  let complete: (response: Response) => void = () => {
    throw new Error("Activation did not start")
  }
  let writes = 0
  await mounted(
    async (container, window) => {
      await context(container, window)
      await click(container, window, "Recover original activation")
      assert.equal(writes, 1)
      await click(container, window, "Cancel waiting")
      assert.match(container.textContent ?? "", /does not prove rollback/)
      await act(async () => complete(Response.json(receipt)))
      assert.doesNotMatch(container.textContent ?? "", /Activation confirmed/)
      assert.equal(writes, 1)
      assert.equal(
        container.querySelector<HTMLInputElement>(
          "input[aria-label='Original activation key']"
        )?.value,
        key
      )
    },
    async (input, init) => {
      if (new Request(input, init).method === "GET") return session()
      writes++
      return new Promise<Response>((resolve) => {
        complete = resolve
      })
    }
  )
})
