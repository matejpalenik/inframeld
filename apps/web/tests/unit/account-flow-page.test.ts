import assert from "node:assert/strict"
import { test } from "node:test"
import { setImmediate as nextTurn } from "node:timers/promises"
import { createElement } from "react"
import { renderToStaticMarkup } from "react-dom/server"
import { loadAccountFlow } from "../../lib/account/flow-page"
import { KratosFlowForm } from "../../components/account/kratos-flow-form"

const origin = "https://inframeld.account.test:8443"
const id = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"
const env = {
  INFRAMELD_ACCOUNT_PUBLIC_ORIGIN: origin,
  INFRAMELD_ACCOUNT_HYDRA_ORIGIN: "https://hydra.account.test:8443",
  INFRAMELD_ACCOUNT_API_INTERNAL_URL: "http://backend:8000",
  INFRAMELD_ACCOUNT_KRATOS_INTERNAL_URL: "http://kratos:4433",
}

const successorId = "d2fab4f4-ffce-4e5a-ae73-25cbff832765"
const thirdId = "e3fab4f4-ffce-4e5a-ae73-25cbff832766"
const identityId = "91fab4f4-ffce-4e5a-ae73-25cbff832767"
const completion = {
  id: 1050001,
  type: "success",
  text: "Your changes have been saved!",
}
const successor = {
  id: successorId,
  type: "browser",
  state: "show_form",
  identity: { id: identityId, traits: { email: "PRIVATE-IDENTITY-TRAIT" } },
  ui: {
    action: `${origin}/self-service/settings?flow=${successorId}`,
    method: "POST",
    nodes: [
      {
        type: "input",
        group: "default",
        attributes: {
          node_type: "input",
          name: "csrf_token",
          type: "hidden",
          value: "native-csrf",
          disabled: false,
        },
        messages: [],
        meta: {},
      },
      {
        type: "input",
        group: "totp",
        attributes: {
          node_type: "input",
          name: "totp_unlink",
          type: "submit",
          value: "true",
          disabled: false,
          required: true,
        },
        messages: [],
        meta: {},
      },
    ],
  },
}
const successfulOriginal = {
  ...successor,
  id,
  state: "success",
  ui: {
    ...successor.ui,
    messages: [
      { ...completion, context: { internal: "PRIVATE-COMPLETION-CONTEXT" } },
    ],
  },
}

test("settings success resolves its one verified native successor and preserves the original completion message", async () => {
  const requests: Request[] = []
  const view = await loadAccountFlow(
    "settings",
    env,
    id,
    "current-cookie",
    async (input, init) => {
      const request = new Request(input, init)
      requests.push(request)
      assert.equal(request.headers.get("Cookie"), "current-cookie")
      assert.equal(request.headers.get("Authorization"), null)
      assert.equal(request.cache, "no-store")
      assert.equal(request.redirect, "manual")
      return Response.json(
        requests.length === 1 ? successfulOriginal : successor
      )
    }
  )
  assert.equal(view.kind, "ready")
  if (view.kind !== "ready") throw new Error("Expected current settings")
  assert.equal(view.flowId, successorId)
  assert.equal(view.ui.action, successor.ui.action)
  assert.deepEqual(view.completionMessages, [completion])
  assert.deepEqual(
    requests.map((request) => new URL(request.url).searchParams.get("id")),
    [id, successorId]
  )
  assert.doesNotMatch(
    JSON.stringify(view),
    /PRIVATE-IDENTITY-TRAIT|PRIVATE-COMPLETION-CONTEXT|kratosInternalUrl|http:\/\/kratos/
  )
  const html = renderToStaticMarkup(
    createElement(KratosFlowForm, {
      ui: view.ui,
      flowId: view.flowId,
      flowKind: "settings",
      publicOrigin: view.publicOrigin,
      completionMessages: view.completionMessages,
    })
  )
  assert.match(html, /Your changes have been saved!/)
  assert.match(html, /name="totp_unlink"/)
  assert.doesNotMatch(html, /could not be verified|PRIVATE-/)
})

for (const [name, original] of [
  ["non-success", { ...successfulOriginal, state: "show_form" }],
  ["missing-state", { ...successfulOriginal, state: undefined }],
  ["wrong-original-id", { ...successfulOriginal, id: thirdId }],
  ["API-original", { ...successfulOriginal, type: "api" }],
  ["missing-original-identity", { ...successfulOriginal, identity: undefined }],
  [
    "malformed-original-identity",
    { ...successfulOriginal, identity: { id: "PRIVATE-INVALID-IDENTITY" } },
  ],
  [
    "external-action",
    {
      ...successfulOriginal,
      ui: {
        ...successfulOriginal.ui,
        action: `https://outside.test/self-service/settings?flow=${successorId}`,
      },
    },
  ],
  [
    "wrong-endpoint",
    {
      ...successfulOriginal,
      ui: {
        ...successfulOriginal.ui,
        action: `${origin}/self-service/registration?flow=${successorId}`,
      },
    },
  ],
  [
    "wrong-method",
    { ...successfulOriginal, ui: { ...successfulOriginal.ui, method: "GET" } },
  ],
  [
    "duplicate-target",
    {
      ...successfulOriginal,
      ui: {
        ...successfulOriginal.ui,
        action: `${successor.ui.action}&flow=${successorId}`,
      },
    },
  ],
  [
    "extra-query",
    {
      ...successfulOriginal,
      ui: {
        ...successfulOriginal.ui,
        action: `${successor.ui.action}&return_to=PRIVATE-URL`,
      },
    },
  ],
  [
    "invalid-target",
    {
      ...successfulOriginal,
      ui: {
        ...successfulOriginal.ui,
        action: `${origin}/self-service/settings?flow=PRIVATE-INVALID-FLOW`,
      },
    },
  ],
] as const) {
  test(`settings ${name} cannot authorize a successor read`, async () => {
    let calls = 0
    const view = await loadAccountFlow(
      "settings",
      env,
      id,
      "current-cookie",
      async () => {
        calls++
        return Response.json(original)
      }
    )
    assert.equal(view.kind, "stopped")
    assert.equal(calls, 1)
    assert.doesNotMatch(
      JSON.stringify(view),
      /PRIVATE-|successor|completed successfully/
    )
  })
}

for (const [name, next] of [
  ["wrong-id", { ...successor, id: thirdId }],
  ["API", { ...successor, type: "api" }],
  ["other-identity", { ...successor, identity: { id: thirdId } }],
  ["missing-identity", { ...successor, identity: undefined }],
  [
    "second-hop",
    {
      ...successor,
      state: "success",
      ui: {
        ...successor.ui,
        action: `${origin}/self-service/settings?flow=${thirdId}`,
      },
    },
  ],
  [
    "backward-hop",
    {
      ...successor,
      ui: {
        ...successor.ui,
        action: `${origin}/self-service/settings?flow=${id}`,
      },
    },
  ],
  [
    "wrong-action-method",
    { ...successor, ui: { ...successor.ui, method: "GET" } },
  ],
  [
    "wrong-action-origin",
    {
      ...successor,
      ui: {
        ...successor.ui,
        action: `https://outside.test/self-service/settings?flow=${successorId}`,
      },
    },
  ],
] as const) {
  test(`settings successor ${name} stops without another hop or original success claim`, async () => {
    let calls = 0
    const view = await loadAccountFlow(
      "settings",
      env,
      id,
      "current-cookie",
      async () => {
        calls++
        return Response.json(calls === 1 ? successfulOriginal : next)
      }
    )
    assert.equal(view.kind, "stopped")
    assert.equal(calls, 2)
    assert.doesNotMatch(JSON.stringify(view), /Your changes|PRIVATE-/)
  })
}

for (const status of [404, 503, "transport"] as const) {
  test(`settings successor ${status} stays safely unavailable without retry or stale success`, async () => {
    let calls = 0
    const view = await loadAccountFlow(
      "settings",
      env,
      id,
      "current-cookie",
      async () => {
        calls++
        if (calls === 1) return Response.json(successfulOriginal)
        if (status === "transport") throw new Error("PRIVATE-PROVIDER-ERROR")
        return Response.json({ message: "PRIVATE-PROVIDER-ERROR" }, { status })
      }
    )
    assert.equal(view.kind, "stopped")
    assert.equal(calls, 2)
    assert.doesNotMatch(JSON.stringify(view), /PRIVATE-|Your changes/)
  })
}

test("current settings with an exact action remains a one-read flow", async () => {
  let calls = 0
  const view = await loadAccountFlow(
    "settings",
    env,
    successorId,
    "current-cookie",
    async () => {
      calls++
      return Response.json(successor)
    }
  )
  assert.equal(view.kind, "ready")
  if (view.kind !== "ready") throw new Error("Expected settings")
  assert.equal(view.flowId, successorId)
  assert.deepEqual(view.completionMessages, [])
  assert.equal(calls, 1)
})

test("settings successor shares the original eight-second deadline after the first read completes", async (t) => {
  const deadlines: AbortController[] = []
  t.mock.method(AbortSignal, "timeout", (milliseconds: number) => {
    assert.equal(milliseconds, 8_000)
    const controller = new AbortController()
    deadlines.push(controller)
    return controller.signal
  })
  let secondStarted: () => void = () => {
    throw new Error("Successor observation was not initialized")
  }
  const observed = new Promise<void>((resolve) => {
    secondStarted = resolve
  })
  let calls = 0
  const operation = loadAccountFlow(
    "settings",
    env,
    id,
    "current-cookie",
    async (_input, init) => {
      calls++
      if (calls === 1) return Response.json(successfulOriginal)
      const signal = init?.signal
      assert.ok(signal)
      secondStarted()
      return new Promise<Response>((_resolve, reject) => {
        if (signal.aborted) reject(signal.reason)
        else
          signal.addEventListener("abort", () => reject(signal.reason), {
            once: true,
          })
      })
    }
  )
  try {
    await Promise.race([
      observed,
      operation.then(() => {
        throw new Error("The successor was not read")
      }),
    ])
    deadlines[0].abort(
      new DOMException("Original deadline elapsed", "TimeoutError")
    )
    const view = await Promise.race([
      operation,
      nextTurn().then(() => {
        throw new Error("Original deadline did not cancel the successor")
      }),
    ])
    assert.equal(view.kind, "stopped")
    assert.equal(calls, 2)
  } finally {
    for (const deadline of deadlines) deadline.abort()
    await operation
  }
})

for (const kind of [
  "registration",
  "verification",
  "recovery",
  "settings",
] as const) {
  test(`starts ${kind} at the fixed public native browser endpoint`, async () => {
    let calls = 0
    const view = await loadAccountFlow(kind, env, undefined, "", async () => {
      calls++
      throw new Error("No flow read is needed before native creation")
    })
    assert.deepEqual(view, {
      kind: "start",
      redirectTo: `${origin}/self-service/${kind}/browser`,
    })
    assert.equal(calls, 0)
  })

  test(`loads ${kind} with the current browser cookie without product admission`, async () => {
    const ui = {
      action: `${origin}/self-service/${kind}?flow=${id}`,
      method: "POST",
      nodes: [],
    }
    let calls = 0
    const view = await loadAccountFlow(
      kind,
      env,
      id,
      "ory_kratos_session=current",
      async (input, init) => {
        calls++
        const request = new Request(input, init)
        assert.equal(
          request.url,
          `http://kratos:4433/self-service/${kind}/flows?id=${id}`
        )
        assert.equal(
          request.headers.get("Cookie"),
          "ory_kratos_session=current"
        )
        return Response.json({ id, type: "browser", ui })
      }
    )
    assert.equal(view.kind, "ready")
    if (view.kind !== "ready") throw new Error("Expected the native flow")
    assert.equal(view.flowId, id)
    assert.equal(view.publicOrigin, origin)
    assert.equal(view.ui.action, ui.action)
    assert.equal(calls, 1)
    assert.doesNotMatch(
      JSON.stringify(view),
      /apiInternalUrl|kratosInternalUrl|http:\/\/kratos/
    )
  })

  test(`invalid ${kind} selectors stop before provider work and are not reflected`, async () => {
    for (const flow of [[id, id], "PRIVATE-INVALID-FLOW"]) {
      let calls = 0
      const view = await loadAccountFlow(kind, env, flow, "", async () => {
        calls++
        throw new Error("No provider request is permitted")
      })
      assert.equal(view.kind, "stopped")
      assert.doesNotMatch(
        JSON.stringify(view),
        /PRIVATE-INVALID-FLOW|No provider request/
      )
      assert.equal(calls, 0)
    }
  })

  test(`unavailable ${kind} stays incomplete without exposing or retrying provider errors`, async () => {
    let calls = 0
    const view = await loadAccountFlow(kind, env, id, "", async () => {
      calls++
      throw new Error("PRIVATE-PROVIDER-ERROR")
    })
    assert.equal(view.kind, "stopped")
    assert.doesNotMatch(
      JSON.stringify(view),
      /PRIVATE-PROVIDER-ERROR|completed successfully|account ready/
    )
    assert.equal(calls, 1)
  })
}
