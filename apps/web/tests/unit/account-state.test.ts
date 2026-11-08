import assert from "node:assert/strict"
import { test } from "node:test"
import { readCurrentIdentity } from "../../lib/account/kratos"
import { inspectAccount } from "../../lib/account/session"

const identity = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"
const other = "499abfc3-6a30-4674-82c2-edc58d8962e4"
const principal = "2c447dc1-fd65-4a88-a425-770f6c614897"
const cookie = "ory_kratos_session=current"
const connection = {
  baseUrl: "http://backend:8000",
  kratosUrl: "http://kratos:4433",
  cookie,
}
const current = (id = identity) =>
  Response.json({
    active: true,
    identity: { id, state: "active", traits: { private: "MUST-NOT-RENDER" } },
  })

test("official session observation returns only the current active identity UUID", async () => {
  const result = await readCurrentIdentity(
    { kratosInternalUrl: connection.kratosUrl },
    cookie,
    async (input, init) => {
      const request = new Request(input, init)
      assert.equal(request.url, "http://kratos:4433/sessions/whoami")
      assert.equal(request.headers.get("Cookie"), cookie)
      assert.equal(request.headers.get("Authorization"), null)
      return current()
    }
  )
  assert.equal(result, identity)
})

test("only an official401 is signed out while unavailable or contradictory identity remains unknown", async () => {
  assert.equal(
    await readCurrentIdentity(
      { kratosInternalUrl: connection.kratosUrl },
      undefined,
      async () => Response.json({}, { status: 401 })
    ),
    null
  )
  for (const reply of [
    () => Response.json({}, { status: 503 }),
    () =>
      Response.json({
        active: false,
        identity: { id: identity, state: "active" },
      }),
    () => current("not-an-identity"),
  ]) {
    await assert.rejects(
      readCurrentIdentity(
        { kratosInternalUrl: connection.kratosUrl },
        cookie,
        async () => reply()
      )
    )
  }
})

test("signed-out account state stops before any product admission request", async () => {
  let calls = 0
  const view = await inspectAccount({
    ...connection,
    fetch: async () => {
      calls++
      return Response.json({}, { status: 401 })
    },
  })
  assert.deepEqual(view, { kind: "signed-out" })
  assert.equal(calls, 1)
})

test("verified identity with product403 reports no admission or recovery diagnosis", async () => {
  const paths: string[] = []
  const view = await inspectAccount({
    ...connection,
    fetch: async (input, init) => {
      const request = new Request(input, init)
      paths.push(new URL(request.url).pathname)
      assert.equal(request.headers.get("Cookie"), cookie)
      assert.equal(request.headers.get("Authorization"), null)
      return paths.length === 2
        ? Response.json(
            { status: 403, code: "access_denied", title: "Denied" },
            { status: 403 }
          )
        : current()
    },
  })
  assert.deepEqual(view, {
    kind: "verified",
    identityId: identity,
    access: { kind: "denied" },
  })
  assert.deepEqual(paths, [
    "/sessions/whoami",
    "/v1/session",
    "/sessions/whoami",
  ])
  assert.doesNotMatch(
    JSON.stringify(view),
    /unadmitted|suspended|recovery|MUST-NOT-RENDER/
  )
})

test("only a validated product session and unchanged current identity show admission", async () => {
  let calls = 0
  const view = await inspectAccount({
    ...connection,
    fetch: async () => {
      calls++
      return calls === 2 ? Response.json({ principalId: principal }) : current()
    },
  })
  assert.deepEqual(view, {
    kind: "verified",
    identityId: identity,
    access: { kind: "admitted", principalId: principal },
  })
  assert.equal(calls, 3)
})

test("a switched identity clears the prior product and identity detail instead of retrying", async () => {
  let calls = 0
  const view = await inspectAccount({
    ...connection,
    fetch: async () => {
      calls++
      return calls === 2
        ? Response.json({ principalId: principal })
        : current(calls === 1 ? identity : other)
    },
  })
  assert.deepEqual(view, { kind: "changed" })
  assert.equal(calls, 3)
})

test("provider503 never becomes signed out, verified or an automatic retry", async () => {
  let calls = 0
  const view = await inspectAccount({
    ...connection,
    fetch: async () => {
      calls++
      return Response.json({}, { status: 503 })
    },
  })
  assert.deepEqual(view, { kind: "unavailable" })
  assert.equal(calls, 1)
})

test("invalid or unavailable product responses do not establish admission", async () => {
  for (const reply of [
    () => Response.json({ principalId: 7 }),
    () => Response.json({}, { status: 503 }),
  ]) {
    let calls = 0
    const view = await inspectAccount({
      ...connection,
      fetch: async () => {
        calls++
        return calls === 2 ? reply() : current()
      },
    })
    assert.deepEqual(view, {
      kind: "verified",
      identityId: identity,
      access: { kind: "unavailable" },
    })
    assert.equal(calls, 3)
  }
})

test("caller cancellation stops before provider or product work", async () => {
  const controller = new AbortController()
  const reason = new Error("Cancelled account observation")
  controller.abort(reason)
  let calls = 0
  await assert.rejects(
    inspectAccount({
      ...connection,
      signal: controller.signal,
      fetch: async () => {
        calls++
        return current()
      },
    }),
    (error) => error === reason
  )
  assert.equal(calls, 0)
})
