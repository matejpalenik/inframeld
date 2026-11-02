import assert from "node:assert/strict"
import { test } from "node:test"
import { accountContentSecurityPolicy } from "../../lib/account/security-headers"
import { proxy } from "../../proxy"

const env = {
  INFRAMELD_ACCOUNT_PUBLIC_ORIGIN: "https://inframeld.account.test:8443",
  INFRAMELD_ACCOUNT_HYDRA_ORIGIN: "https://hydra.account.test:8443",
  INFRAMELD_ACCOUNT_API_INTERNAL_URL: "http://backend:8000",
  INFRAMELD_ACCOUNT_KRATOS_INTERNAL_URL: "http://kratos:4433",
}

test("native form redirect policy permits only self and the current vetted Hydra HTTPS origin", () => {
  assert.equal(
    accountContentSecurityPolicy(env),
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://hydra.account.test:8443"
  )
  assert.equal(
    accountContentSecurityPolicy({
      ...env,
      INFRAMELD_ACCOUNT_HYDRA_ORIGIN: "https://other-issuer.example.test",
    }),
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://other-issuer.example.test"
  )
})

test("missing or malformed account configuration cannot broaden form destinations", () => {
  for (const hydra of [
    undefined,
    "https://*.example.test",
    "https://hydra.account.test;",
    "https://hydra.account.test,other",
    "http://hydra.account.test:8443",
    "https://hydra.account.test:8443/path",
    "https://user@hydra.account.test:8443",
    "https://hydra.account.test:8443; form-action *",
    env.INFRAMELD_ACCOUNT_PUBLIC_ORIGIN,
  ]) {
    assert.equal(
      accountContentSecurityPolicy({
        ...env,
        INFRAMELD_ACCOUNT_HYDRA_ORIGIN: hydra,
      }),
      "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
  }
})

test("account response policy reads the server origin at request time and has no forwarding side effects", () => {
  const previous = Object.fromEntries(
    Object.keys(env).map((key) => [key, process.env[key]])
  )
  try {
    Object.assign(process.env, env)
    const first = proxy()
    assert.match(
      first.headers.get("Content-Security-Policy") ?? "",
      /https:\/\/hydra.account.test:8443$/
    )
    process.env.INFRAMELD_ACCOUNT_HYDRA_ORIGIN =
      "https://replacement.example.test"
    const second = proxy()
    assert.match(
      second.headers.get("Content-Security-Policy") ?? "",
      /https:\/\/replacement.example.test$/
    )
    assert.equal(second.headers.get("location"), null)
    assert.equal(second.headers.get("set-cookie"), null)
    assert.equal(second.headers.get("Origin"), null)
  } finally {
    for (const [key, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
})
