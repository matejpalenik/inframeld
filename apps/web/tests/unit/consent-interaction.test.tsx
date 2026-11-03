import assert from "node:assert/strict"
import { test } from "node:test"
import { JSDOM } from "jsdom"
import { act } from "react"
import type { HumanOAuthConsentDetailsResponse } from "@inframeld/sdk"
import { ConsentForm } from "../../app/(account)/consent/consent-form"

const origin = "https://inframeld.account.test:8443"
const details: HumanOAuthConsentDetailsResponse = {
  accountSubject: "alice-id",
  installation: origin,
  clientId: "inframeld-cli",
  requestedScopes: ["openid", "inframeld:api"],
  requestedAudience: [origin],
  approvalRequired: true,
  rememberConsentSeconds: 3600,
}

async function mounted(
  run: (container: HTMLElement, window: JSDOM["window"]) => Promise<void>,
  fetch?: typeof globalThis.fetch
) {
  const dom = new JSDOM("<!DOCTYPE html><div id='root'></div>", {
    url: `${origin}/consent?consent_challenge=private`,
  })
  const values = {
    window: dom.window,
    document: dom.window.document,
    HTMLButtonElement: dom.window.HTMLButtonElement,
    IS_REACT_ACT_ENVIRONMENT: true,
  }
  const previous = Object.fromEntries(
    Object.keys(values).map((key) => [
      key,
      Object.getOwnPropertyDescriptor(globalThis, key),
    ])
  )
  const transport = globalThis.fetch
  if (fetch) globalThis.fetch = fetch
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
      root.render(
        <ConsentForm
          initialView={{ kind: "ready", details }}
          challenge="private"
          publicOrigin={origin}
          hydraOrigin="https://hydra.account.test:8443"
        />
      )
    )
    await run(container, dom.window)
  } finally {
    await act(async () => root.unmount())
    dom.window.close()
    globalThis.fetch = transport
    for (const [key, descriptor] of Object.entries(previous)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else Reflect.deleteProperty(globalThis, key)
    }
  }
}

test("consent has no mount mutation and duplicate allow clicks dispatch only once after a lost response", async () => {
  let posts = 0
  await mounted(
    async (container, window) => {
      assert.equal(posts, 0)
      const form = container.querySelector("form")!
      const button = container.querySelector<HTMLButtonElement>(
        'button[value="allow"]'
      )!
      await act(async () => {
        form.dispatchEvent(
          new window.SubmitEvent("submit", {
            bubbles: true,
            cancelable: true,
            submitter: button,
          })
        )
        form.dispatchEvent(
          new window.SubmitEvent("submit", {
            bubbles: true,
            cancelable: true,
            submitter: button,
          })
        )
      })
      assert.equal(posts, 1)
      assert.match(
        container.textContent ?? "",
        /outcome could not be confirmed/
      )
      assert.doesNotMatch(
        container.textContent ?? "",
        /alice-id|Allow CLI access/
      )
      assert.equal(window.document.activeElement?.getAttribute("role"), "alert")
    },
    async (input) => {
      if (new Request(input).method === "POST") posts += 1
      throw new Error("Lost provider response")
    }
  )
})

test("an inspection completed after a page loses focus cannot restore protected consent details", async () => {
  await mounted(async (container, window) => {
    let complete: (response: Response) => void = () => {
      throw new Error("Inspection did not start")
    }
    globalThis.fetch = () =>
      new Promise<Response>((resolve) => {
        complete = resolve
      })
    await act(async () => {
      window.dispatchEvent(new window.Event("focus"))
    })
    assert.doesNotMatch(container.textContent ?? "", /alice-id/)
    await act(async () => {
      window.dispatchEvent(new window.Event("blur"))
    })
    await act(async () => {
      complete(
        new Response(JSON.stringify(details), {
          headers: { "Content-Type": "application/json" },
        })
      )
    })
    assert.doesNotMatch(
      container.textContent ?? "",
      /alice-id|Allow CLI access/
    )
  })
})

test("a restored page clears details after a controlled expired-session401", async () => {
  await mounted(async (container, window) => {
    let reads = 0
    globalThis.fetch = async () => {
      reads += 1
      return new Response(
        JSON.stringify({
          type: "about:blank",
          title: "Unauthorized",
          status: 401,
          detail: "The browser session expired.",
          requestId: "expired-session",
        }),
        {
          status: 401,
          headers: { "Content-Type": "application/problem+json" },
        }
      )
    }
    await act(async () => {
      window.dispatchEvent(
        new window.PageTransitionEvent("pageshow", { persisted: true })
      )
    })
    assert.equal(reads, 1)
    assert.doesNotMatch(
      container.textContent ?? "",
      /alice-id|Allow CLI access/
    )
    assert.match(container.textContent ?? "", /browser session is unavailable/)
  })
})

test("pending decision status remains visible after blur without showing account details or dispatching again", async () => {
  let posts = 0
  let complete: (response: Response) => void = () => {
    throw new Error("Decision did not start")
  }
  await mounted(
    async (container, window) => {
      const form = container.querySelector("form")!
      const button = container.querySelector<HTMLButtonElement>(
        'button[value="allow"]'
      )!
      await act(async () => {
        form.dispatchEvent(
          new window.SubmitEvent("submit", {
            bubbles: true,
            cancelable: true,
            submitter: button,
          })
        )
      })
      await act(async () => {
        window.dispatchEvent(new window.Event("blur"))
        window.dispatchEvent(new window.Event("focus"))
      })
      const status = container.querySelector('[role="status"]')!
      assert.match(status.textContent ?? "", /Sending your decision/)
      const statusVisible = status.closest("[hidden]") === null
      const detailsHidden =
        container.querySelector("dl")?.closest("[hidden]") !== null
      await act(async () => {
        complete(
          new Response("{}", {
            status: 503,
            headers: { "Content-Type": "application/problem+json" },
          })
        )
      })
      assert.equal(statusVisible, true)
      assert.equal(detailsHidden, true)
      assert.equal(posts, 1)
      assert.match(
        container.textContent ?? "",
        /outcome could not be confirmed/
      )
    },
    (input) => {
      if (new Request(input).method === "POST") posts += 1
      return new Promise<Response>((resolve) => {
        complete = resolve
      })
    }
  )
})
