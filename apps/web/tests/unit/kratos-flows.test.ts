import assert from "node:assert/strict"
import { test } from "node:test"
import {
  readRecoveryFlow,
  readRegistrationFlow,
  readSettingsFlow,
  readVerificationFlow,
} from "../../lib/account/kratos"

const origin = "https://inframeld.account.test:8443"
const id = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"
const cookie = "ory_kratos_session=current; native_csrf=cookie"
const config = {
  publicOrigin: origin,
  hydraOrigin: "https://hydra.account.test:8443",
  apiInternalUrl: "http://backend:8000",
  kratosInternalUrl: "http://kratos:4433",
  oidcFormActionOrigins: [],
}

for (const [kind, read] of [
  ["registration", readRegistrationFlow],
  ["verification", readVerificationFlow],
  ["recovery", readRecoveryFlow],
  [
    "settings",
    async (...args: Parameters<typeof readSettingsFlow>) =>
      (await readSettingsFlow(...args)).flow,
  ],
] as const) {
  const flow = {
    id,
    type: "browser",
    ui: {
      action: `${origin}/self-service/${kind}?flow=${id}`,
      method: "POST",
      nodes: [],
    },
  }

  test(`reads the exact ${kind} browser flow using the official cookie client`, async () => {
    let seen: Request | undefined
    const result = await read(config, id, cookie, async (url, init) => {
      seen = new Request(url, init)
      return Response.json(flow)
    })
    assert.equal(result.id, id)
    assert.equal(result.type, "browser")
    assert.equal(
      seen?.url,
      `http://kratos:4433/self-service/${kind}/flows?id=${id}`
    )
    assert.equal(seen?.headers.get("Cookie"), cookie)
    assert.equal(seen?.headers.get("Authorization"), null)
    assert.equal(seen?.cache, "no-store")
    assert.equal(seen?.redirect, "manual")
  })

  test(`refuses mismatched and API ${kind} flows without following a redirect`, async () => {
    for (const reply of [
      () => Response.json({ ...flow, type: "api" }),
      () =>
        Response.json({ ...flow, id: "00000000-0000-0000-0000-000000000000" }),
      () =>
        new Response(null, {
          status: 302,
          headers: { Location: "https://outside.test/" },
        }),
    ]) {
      let calls = 0
      await assert.rejects(
        read(config, id, cookie, async () => {
          calls++
          return reply()
        })
      )
      assert.equal(calls, 1)
    }
  })
}
