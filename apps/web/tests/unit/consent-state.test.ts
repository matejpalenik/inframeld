import assert from "node:assert/strict"
import { test } from "node:test"
import { decideConsent, inspectConsent } from "../../lib/account/consent"
import { accountConfig } from "../../lib/account/config"

const baseUrl = "https://inframeld.account.test:8443"
const hydra = "https://hydra.account.test:8443"
const details = {
  accountSubject: "c1fab4f4-ffce-4e5a-ae73-25cbff832764",
  approvalRequired: true,
  clientId: "inframeld-cli",
  installation: baseUrl,
  rememberConsentSeconds: 3600,
  requestedAudience: [baseUrl],
  requestedScopes: ["openid", "offline_access", "inframeld:api"],
}

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type":
        status === 200 ? "application/json" : "application/problem+json",
    },
  })
}

test("uses generated inspection with the exact current cookie and challenge", async () => {
  let seen: Request | undefined
  const result = await inspectConsent({
    baseUrl,
    challenge: "challenge-private",
    cookie: "ory_kratos_session=current",
    fetch: async (input) => {
      seen = new Request(input)
      return response(details)
    },
  })
  assert.deepEqual(result, { kind: "ready", details })
  assert.equal(seen?.method, "GET")
  assert.equal(seen?.headers.get("Cookie"), "ory_kratos_session=current")
  assert.equal(seen?.headers.get("Authorization"), null)
  assert.equal(
    new URL(seen!.url).searchParams.get("consent_challenge"),
    "challenge-private"
  )
  assert.equal(seen?.cache, "no-store")
})

test("posts only the native consent decision and follows a checked Hydra continuation", async () => {
  let seen: Request | undefined
  const redirectTo = `${hydra}/oauth2/auth?consent_verifier=private`
  const result = await decideConsent(
    {
      baseUrl,
      challenge: "challenge-private",
      fetch: async (input) => {
        seen = new Request(input)
        return response({ redirectTo })
      },
    },
    "allow",
    false,
    hydra
  )
  assert.deepEqual(result, { kind: "continue", redirectTo })
  assert.equal(seen?.headers.get("X-Inframeld-CSRF"), "1")
  assert.equal(seen?.headers.get("Authorization"), null)
  assert.equal(seen?.headers.get("Origin"), null, "the browser supplies Origin")
  assert.deepEqual(await seen!.json(), {
    consentChallenge: "challenge-private",
    decision: "allow",
    remember: false,
  })
})

test("denial does not submit remembered approval", async () => {
  let body: unknown
  await decideConsent(
    {
      baseUrl,
      challenge: "private",
      fetch: async (input) => {
        body = await new Request(input).json()
        return response({
          redirectTo: `${hydra}/oauth2/auth?consent_verifier=denied`,
        })
      },
    },
    "deny",
    true,
    hydra
  )
  assert.deepEqual(body, {
    consentChallenge: "private",
    decision: "deny",
    remember: false,
  })
})

test("one local approval follows only the configured Hydra continuation", async () => {
  const { hydraOrigin } = accountConfig({
    INFRAMELD_ACCOUNT_TRANSPORT: "managed-local",
    INFRAMELD_ACCOUNT_PUBLIC_ORIGIN: "http://127.0.0.1:8001",
    INFRAMELD_ACCOUNT_HYDRA_ORIGIN: "http://127.0.0.1:14444",
    INFRAMELD_ACCOUNT_API_INTERNAL_URL: "http://backend:8000",
    INFRAMELD_ACCOUNT_KRATOS_INTERNAL_URL: "http://kratos:4433",
  })
  const redirectTo = `${hydraOrigin}/oauth2/auth?consent_verifier=private`
  let calls = 0
  const result = await decideConsent(
    {
      baseUrl,
      challenge: "private",
      fetch: async () => {
        calls++
        return response({ redirectTo })
      },
    },
    "allow",
    false,
    hydraOrigin
  )
  assert.deepEqual(result, { kind: "continue", redirectTo })
  assert.equal(calls, 1)
})

test("does not follow a forged or wrong-path continuation", async () => {
  for (const redirectTo of [
    "https://evil.test/oauth2/auth",
    `${hydra}/admin`,
    `${hydra}/oauth2/auth#private`,
  ]) {
    const result = await decideConsent(
      {
        baseUrl,
        challenge: "private",
        fetch: async () => response({ redirectTo }),
      },
      "allow",
      false,
      hydra
    )
    assert.equal(result.kind, "stopped")
    if (result.kind === "stopped") assert.equal(result.uncertain, true)
  }
})

test("lost or malformed approval responses remain unknown with one dispatch", async () => {
  for (const fetch of [
    async () => {
      throw new Error("private upstream secret")
    },
    async () => response({ bad: "private challenge" }),
  ]) {
    let calls = 0
    const result = await decideConsent(
      {
        baseUrl,
        challenge: "private",
        fetch: async () => {
          calls++
          return fetch()
        },
      },
      "allow",
      false,
      hydra
    )
    assert.equal(calls, 1)
    assert.equal(result.kind, "stopped")
    if (result.kind === "stopped") {
      assert.equal(result.uncertain, true)
      assert.doesNotMatch(result.message, /secret|challenge|upstream/)
    }
  }
})

test("a controlled expired-session401 removes protected inspection details", async () => {
  const problem = {
    type: "about:blank",
    title: "Unauthorized",
    status: 401,
    detail: "private provider detail",
    requestId: "request",
  }
  const result = await inspectConsent({
    baseUrl,
    challenge: "private",
    fetch: async () => response(problem, 401),
  })
  assert.equal(result.kind, "stopped")
  assert.doesNotMatch(JSON.stringify(result), /provider detail|accountSubject/)
})
