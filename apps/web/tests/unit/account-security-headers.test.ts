import assert from "node:assert/strict"
import { test } from "node:test"
import nextTesting from "next/experimental/testing/server"
import { accountContentSecurityPolicy } from "../../lib/account/security-headers"
import { config, proxy } from "../../proxy"
import { accountConfig } from "../../lib/account/config"

const env = {
  INFRAMELD_ACCOUNT_PUBLIC_ORIGIN: "https://inframeld.account.test:8443",
  INFRAMELD_ACCOUNT_HYDRA_ORIGIN: "https://hydra.account.test:8443",
  INFRAMELD_ACCOUNT_API_INTERNAL_URL: "http://backend:8000",
  INFRAMELD_ACCOUNT_KRATOS_INTERNAL_URL: "http://kratos:4433",
}
const { unstable_doesMiddlewareMatch } = nextTesting

for (const path of [
  "/registration",
  "/verification",
  "/recovery",
  "/settings",
]) {
  test(`native account route ${path} receives the account response policy`, () => {
    assert.equal(
      unstable_doesMiddlewareMatch({
        config,
        nextConfig: {},
        url: `${env.INFRAMELD_ACCOUNT_PUBLIC_ORIGIN}${path}?flow=c1fab4f4-ffce-4e5a-ae73-25cbff832764`,
      }),
      true
    )
  })
}

test("the account response policy does not intercept unrelated static assets", () => {
  assert.equal(
    unstable_doesMiddlewareMatch({
      config,
      nextConfig: {},
      url: "/_next/static/example.js",
    }),
    false
  )
})

test("the optional OIDC form-navigation list defaults to empty", () => {
  assert.deepEqual(accountConfig(env).oidcFormActionOrigins, [])
})

test("only configured canonical OIDC origins extend form navigation", () => {
  const configured = {
    ...env,
    INFRAMELD_ACCOUNT_OIDC_FORM_ACTION_ORIGINS:
      '["https://login.company.example/","https://other.company.example"]',
  }
  assert.deepEqual(accountConfig(configured).oidcFormActionOrigins, [
    "https://login.company.example",
    "https://other.company.example",
  ])
  assert.equal(
    accountContentSecurityPolicy(configured),
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self' https://hydra.account.test:8443 https://login.company.example https://other.company.example"
  )
})

for (const input of [
  "",
  "null",
  '"https://login.company.example"',
  "[true]",
  "[7]",
  '["http://login.company.example"]',
  '["https://*.company.example"]',
  '["https://user:password@login.company.example"]',
  '["https://login.company.example/authorize"]',
  '["https://login.company.example?state=private"]',
  '["https://login.company.example#fragment"]',
  '["https://login.company.example;form-action"]',
  '[" https://login.company.example"]',
  '["https://login.company.example","https://login.company.example/"]',
  '["https://login.company.example","http://other.company.example"]',
  JSON.stringify(
    Array.from({ length: 9 }, (_, index) => `https://company-${index}.example`)
  ),
  JSON.stringify([`https://${"a".repeat(4096)}.example`]),
] as const) {
  test(`invalid OIDC navigation configuration ${input.length > 100 ? "exceeds the bounded list" : input} stays completely closed`, () => {
    const configured = {
      ...env,
      INFRAMELD_ACCOUNT_OIDC_FORM_ACTION_ORIGINS: input,
    }
    assert.throws(() => accountConfig(configured))
    assert.equal(
      accountContentSecurityPolicy(configured),
      "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
  })
}

test("proxy reads the optional OIDC navigation policy for each request", () => {
  const key = "INFRAMELD_ACCOUNT_OIDC_FORM_ACTION_ORIGINS"
  const configured = { ...env, [key]: '["https://login.company.example"]' }
  const previous = Object.fromEntries(
    Object.keys(configured).map((name) => [name, process.env[name]])
  )
  try {
    Object.assign(process.env, configured)
    assert.match(
      proxy().headers.get("Content-Security-Policy") ?? "",
      / https:\/\/login\.company\.example$/
    )
    process.env[key] = '["https://other.company.example"]'
    const next = proxy()
    assert.match(
      next.headers.get("Content-Security-Policy") ?? "",
      / https:\/\/other\.company\.example$/
    )
    assert.doesNotMatch(
      next.headers.get("Content-Security-Policy") ?? "",
      /login\.company/
    )
    assert.equal(next.headers.get("location"), null)
  } finally {
    for (const [name, value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[name]
      else process.env[name] = value
    }
  }
})

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
