import assert from "node:assert/strict"
import { test } from "node:test"
import {
  activateOriginalInvitation,
  currentInvitationIdentity,
  inspectInvitation,
  invitationOriginal,
} from "../../lib/account/invitations"

const origin = "https://inframeld.account.test:8443"
const identity = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"
const other = "499abfc3-6a30-4674-82c2-edc58d8962e4"
const invitation = "2c447dc1-fd65-4a88-a425-770f6c614897"
const organization = "210b369f-e208-484d-9a0b-2c2c5409ba24"
const token = "a".repeat(43)
const key = "original-request:preserve-exactly"
const original = {
  identityId: identity,
  token,
  key,
  method: "POST" as const,
  route: "/v1/invitations/activate" as const,
}
const preview = {
  invitationId: invitation,
  organizationId: organization,
  assignments: [{ kind: "admission-only" }],
  scopes: [
    {
      target: { kind: "organization", organizationId: organization },
      displayName: "Support",
    },
  ],
  expiresAt: "2026-11-09T12:00:00Z",
}
const receipt = {
  invitationId: invitation,
  organizationId: organization,
  principalId: other,
  operationId: key,
  organizationAccessRevision: 3,
  projectAccessRevisions: [],
  idempotencyExpiresAt: "2026-11-09T12:00:00Z",
}
const current = (id = identity) =>
  Response.json({ active: true, identity: { id, state: "active" } })
const problem = (status: number) =>
  Response.json(
    {
      status,
      code: status === 404 ? "resource_not_found" : "access_denied",
      type: "https://inframeld.test/problems/stopped",
      title: "Stopped",
      detail: "PRIVATE PROVIDER DETAIL MUST NOT BE RENDERED",
      requestId: invitation,
    },
    { status, headers: { "Content-Type": "application/problem+json" } }
  )

test("original binding preserves exact input immutably without dispatch", () => {
  const saved = invitationOriginal(identity, token, key)
  assert.deepEqual(saved, original)
  assert.ok(Object.isFrozen(saved))
  assert.throws(() => Object.assign(saved, { key: "different" }))
})

for (const [badIdentity, badToken, badKey] of [
  ["invalid", token, key],
  [identity, "", key],
  [identity, `${token} `, key],
  [identity, token, " "],
  [identity, token, "a".repeat(129)],
  [identity, token, "unsafe\r\nheader"],
  [identity, token, " padded-original "],
  [identity, token, "\toriginal"],
]) {
  test("invalid original context fails safely before any provider request", () => {
    assert.throws(
      () => invitationOriginal(badIdentity!, badToken!, badKey!),
      (error) => {
        assert.ok(error instanceof Error)
        assert.doesNotMatch(error.message, new RegExp(token))
        return true
      }
    )
  })
}

test("current recipient identity does not require a product admission read", async () => {
  const paths: string[] = []
  assert.equal(
    await currentInvitationIdentity({
      publicOrigin: origin,
      fetch: async (input, init) => {
        const request = new Request(input, init)
        paths.push(new URL(request.url).pathname)
        assert.equal(request.credentials, "same-origin")
        assert.equal(request.headers.get("Cookie"), null)
        assert.equal(request.headers.get("Authorization"), null)
        return current()
      },
    }),
    identity
  )
  assert.deepEqual(paths, ["/sessions/whoami"])
})

test("preview uses generated cookie profile and marker without a key, then rechecks identity", async () => {
  const paths: string[] = []
  const view = await inspectInvitation(
    {
      publicOrigin: origin,
      fetch: async (input, init) => {
        const request = new Request(input, init)
        paths.push(new URL(request.url).pathname)
        if (request.method === "GET") return current()
        assert.equal(request.credentials, "same-origin")
        assert.equal(request.cache, "no-store")
        assert.equal(request.redirect, "manual")
        assert.equal(request.headers.get("Authorization"), null)
        assert.equal(request.headers.get("Cookie"), null)
        assert.equal(request.headers.get("Origin"), null)
        assert.equal(request.headers.get("Idempotency-Key"), null)
        assert.equal(request.headers.get("X-Inframeld-CSRF"), "1")
        assert.deepEqual(await request.json(), { invitationToken: token })
        return Response.json(preview)
      },
    },
    token
  )
  assert.deepEqual(view, { kind: "ready", identityId: identity, preview })
  assert.deepEqual(paths, [
    "/sessions/whoami",
    "/v1/invitations/preview",
    "/sessions/whoami",
  ])
})

test("original recovery sends one exact activation without first previewing a consumed token", async () => {
  const paths: string[] = []
  const result = await activateOriginalInvitation(
    {
      publicOrigin: origin,
      fetch: async (input, init) => {
        const request = new Request(input, init)
        paths.push(new URL(request.url).pathname)
        if (request.method === "GET") return current()
        assert.equal(request.headers.get("Idempotency-Key"), key)
        assert.equal(request.headers.get("X-Inframeld-CSRF"), "1")
        assert.equal(request.headers.get("Authorization"), null)
        assert.equal(request.headers.get("Cookie"), null)
        assert.deepEqual(await request.json(), { invitationToken: token })
        return Response.json(receipt)
      },
    },
    original
  )
  assert.deepEqual(result, { kind: "completed", receipt })
  assert.deepEqual(paths, [
    "/sessions/whoami",
    "/v1/invitations/activate",
    "/sessions/whoami",
  ])
})

for (const signedOut of [false, true]) {
  test("a switched or missing identity prevents original dispatch", async () => {
    let calls = 0
    const result = await activateOriginalInvitation(
      {
        publicOrigin: origin,
        fetch: async () => {
          calls++
          return signedOut ? Response.json({}, { status: 401 }) : current(other)
        },
      },
      original
    )
    assert.deepEqual(result, { kind: "identity-changed" })
    assert.equal(calls, 1)
  })
}

test("a switched identity after a response cannot reveal the former account receipt or scope", async () => {
  for (const mode of ["preview", "activate"] as const) {
    let calls = 0
    const connection = {
      publicOrigin: origin,
      fetch: async () => {
        calls++
        return calls === 2
          ? Response.json(mode === "preview" ? preview : receipt)
          : current(calls === 1 ? identity : other)
      },
    }
    const result =
      mode === "preview"
        ? await inspectInvitation(connection, token)
        : await activateOriginalInvitation(connection, original)
    assert.deepEqual(result, { kind: "identity-changed" })
    assert.equal(calls, 3)
  }
})

for (const status of [401, 403, 404, 409, 503]) {
  test(`safe preview ${status} never returns provider detail or protected token`, async () => {
    let calls = 0
    const result = await inspectInvitation(
      {
        publicOrigin: origin,
        fetch: async () => (++calls === 2 ? problem(status) : current()),
      },
      token
    )
    assert.equal(result.kind, "stopped")
    assert.doesNotMatch(
      JSON.stringify(result),
      /PRIVATE|cleanup completed|suspended|password hash/
    )
    assert.ok(!JSON.stringify(result).includes(token))
  })
}

for (const failure of ["lost", "invalid", "unavailable"] as const) {
  test(`a ${failure} activation response remains uncertain with no redispatch`, async () => {
    let writes = 0
    const result = await activateOriginalInvitation(
      {
        publicOrigin: origin,
        fetch: async (input, init) => {
          const request = new Request(input, init)
          if (request.method === "GET") return current()
          writes++
          if (failure === "lost") throw new Error("PRIVATE NETWORK DETAILS")
          return failure === "invalid"
            ? Response.json({ principalId: 7 })
            : problem(503)
        },
      },
      original
    )
    assert.equal(result.kind, "uncertain")
    assert.equal(writes, 1)
    assert.doesNotMatch(JSON.stringify(result), /PRIVATE|NETWORK/)
  })
}

test("pre-dispatch cancellation does no work while cancellation after dispatch retains uncertainty", async () => {
  const cancelled = new AbortController()
  cancelled.abort(new Error("cancelled"))
  let calls = 0
  await assert.rejects(
    activateOriginalInvitation(
      {
        publicOrigin: origin,
        signal: cancelled.signal,
        fetch: async () => {
          calls++
          return current()
        },
      },
      original
    )
  )
  assert.equal(calls, 0)
  const controller = new AbortController()
  const result = await activateOriginalInvitation(
    {
      publicOrigin: origin,
      signal: controller.signal,
      fetch: async (input, init) => {
        const request = new Request(input, init)
        calls++
        if (request.method === "GET") return current()
        controller.abort()
        throw controller.signal.reason
      },
    },
    original
  )
  assert.equal(result.kind, "uncertain")
  assert.equal(calls, 2)
})
