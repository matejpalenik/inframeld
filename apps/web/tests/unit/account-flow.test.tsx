import assert from "node:assert/strict"
import { test } from "node:test"
import { renderToStaticMarkup } from "react-dom/server"
import type {
  UiContainer,
  UiNode,
  UiNodeInputAttributes,
} from "@ory/client-fetch"
import { KratosFlowForm } from "../../components/account/kratos-flow-form"
import {
  accountConfig,
  checkedProviderUrl,
  singleParameter,
} from "../../lib/account/config"

const origin = "https://inframeld.account.test:8443"
const flowId = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"
const env = {
  INFRAMELD_ACCOUNT_PUBLIC_ORIGIN: origin,
  INFRAMELD_ACCOUNT_HYDRA_ORIGIN: "https://hydra.account.test:8443",
  INFRAMELD_ACCOUNT_API_INTERNAL_URL: "http://backend:8000",
  INFRAMELD_ACCOUNT_KRATOS_INTERNAL_URL: "http://kratos:4433",
}

export function input(
  name: string,
  type: UiNodeInputAttributes["type"],
  value?: string,
  group: "default" | "password" | "code" = "default"
): UiNode {
  return {
    type: "input",
    group,
    attributes: {
      node_type: "input",
      name,
      type,
      value,
      disabled: false,
      required: type !== "submit",
    },
    messages: [],
    meta: { label: { id: 1, text: name, type: "info" } },
  }
}

function form(nodes: UiNode[]): UiContainer {
  return {
    action: `${origin}/self-service/login?flow=${flowId}`,
    method: "POST",
    nodes,
  }
}

function render(ui: UiContainer): string {
  return renderToStaticMarkup(
    <KratosFlowForm ui={ui} publicOrigin={origin} flowId={flowId} />
  )
}

test("uses an explicit HTTPS account and issuer with private fixed upstreams", () => {
  assert.deepEqual(accountConfig(env), {
    publicOrigin: origin,
    hydraOrigin: "https://hydra.account.test:8443",
    apiInternalUrl: "http://backend:8000",
    kratosInternalUrl: "http://kratos:4433",
    oidcFormActionOrigins: [],
  })
})

test("does not turn missing configuration or public HTTP into a login target", () => {
  assert.throws(() => accountConfig({}))
  for (const value of [
    "http://127.0.0.1:3000",
    `${origin}/path`,
    `${origin}?next=x`,
  ]) {
    assert.throws(() =>
      accountConfig({ ...env, INFRAMELD_ACCOUNT_PUBLIC_ORIGIN: value })
    )
  }
})

test("the managed-local profile uses distinct canonical loopback origins", () => {
  const local = {
    ...env,
    INFRAMELD_ACCOUNT_TRANSPORT: "managed-local",
    INFRAMELD_ACCOUNT_PUBLIC_ORIGIN: "http://127.0.0.1:8001",
    INFRAMELD_ACCOUNT_HYDRA_ORIGIN: "http://127.0.0.1:14444/",
  }
  assert.equal(accountConfig(local).publicOrigin, "http://127.0.0.1:8001")
  assert.equal(accountConfig(local).hydraOrigin, "http://127.0.0.1:14444")
  for (const value of [
    "http://localhost:8001",
    "http://127.1:8001",
    "http://127.0.0.2:8001",
    "http://[::1]:8001",
    "http://192.168.1.2:8001",
    "http://127.0.0.1",
    "http://127.0.0.1:80",
    "http://127.0.0.1:08001",
    "http://127.0.0.1:8001/path",
    "http://user@127.0.0.1:8001",
    env.INFRAMELD_ACCOUNT_PUBLIC_ORIGIN,
  ]) {
    assert.throws(() =>
      accountConfig({ ...local, INFRAMELD_ACCOUNT_PUBLIC_ORIGIN: value })
    )
    assert.throws(() =>
      accountConfig({ ...local, INFRAMELD_ACCOUNT_HYDRA_ORIGIN: value })
    )
  }
  assert.throws(() =>
    accountConfig({
      ...local,
      INFRAMELD_ACCOUNT_HYDRA_ORIGIN: local.INFRAMELD_ACCOUNT_PUBLIC_ORIGIN,
    })
  )
  assert.throws(() =>
    accountConfig({ ...env, INFRAMELD_ACCOUNT_TRANSPORT: "unknown" })
  )
})

test("renders a native local form only for the configured canonical action", () => {
  const local = "http://127.0.0.1:8001"
  const path = "/self-service/login"
  const action = `${local}${path}?flow=${flowId}`
  const ui = form([
    input("csrf_token", "hidden", "native-token"),
    input("identifier", "text", "alice@example.test", "password"),
    input("password", "password", undefined, "password"),
    input("method", "submit", "password", "password"),
  ])
  const markup = renderToStaticMarkup(
    <KratosFlowForm
      ui={{ ...ui, action }}
      publicOrigin={local}
      flowId={flowId}
    />
  )
  assert.ok(markup.includes(`action="${action}"`))
  assert.match(markup, /name="csrf_token"[^>]*value="native-token"/)
  for (const value of [
    "http://localhost:8001",
    "http://127.1:8001",
    "http://127.0.0.1:08001",
    "http://127.0.0.1:8002",
    "https://127.0.0.1:8001",
    "http://user@127.0.0.1:8001",
  ]) {
    assert.throws(() => checkedProviderUrl(`${value}${path}`, local, path))
  }
  assert.throws(() =>
    checkedProviderUrl(
      "http://example.test/self-service/login",
      "http://example.test",
      path
    )
  )
})

test("rejects duplicate and malformed flow inputs instead of choosing one", () => {
  assert.equal(singleParameter(flowId, "flow"), flowId)
  assert.equal(singleParameter(undefined, "flow"), undefined)
  for (const value of [[flowId, flowId], "", "../flow", "bad\nvalue"]) {
    assert.throws(() => singleParameter(value, "flow"))
  }
  assert.equal(
    singleParameter("opaque-private-challenge", "challenge"),
    "opaque-private-challenge"
  )
})

test("permits only the configured provider endpoint without userinfo or fragments", () => {
  assert.equal(
    checkedProviderUrl(
      `${origin}/self-service/login?flow=${flowId}`,
      origin,
      "/self-service/login"
    ),
    `${origin}/self-service/login?flow=${flowId}`
  )
  for (const url of [
    `https://evil.test/self-service/login`,
    `${origin}/admin`,
    `${origin}/self-service/login#x`,
    `https://user@inframeld.account.test:8443/self-service/login`,
  ]) {
    assert.throws(() => checkedProviderUrl(url, origin, "/self-service/login"))
  }
})

test("renders the provider password form with native CSRF and method values", () => {
  const html = render(
    form([
      input("csrf_token", "hidden", "native-token"),
      input("identifier", "text", "alice@example.test", "password"),
      input("password", "password", undefined, "password"),
      input("method", "submit", "password", "password"),
    ])
  )
  assert.match(html, /method="post"/)
  assert.match(
    html,
    /action="https:\/\/inframeld.account.test:8443\/self-service\/login\?flow=/
  )
  assert.match(html, /name="csrf_token"[^>]*value="native-token"/)
  assert.match(html, /<button\b(?=[^>]*name="method")(?=[^>]*value="password")/)
  assert.match(html, /type="password"/)
  assert.match(html, /<label[^>]*for=/)
})

test("renders code submission, resend and native messages without declaring login", () => {
  const ui = form([
    input("csrf_token", "hidden", "code-csrf"),
    input("identifier", "hidden", "alice@example.test"),
    input("method", "hidden", "code", "code"),
    input("code", "text", undefined, "code"),
    input("method", "submit", "code", "code"),
    input("resend", "submit", "code", "code"),
  ])
  ui.messages = [{ id: 1, text: "Enter the code sent by email.", type: "info" }]
  ui.nodes[3].messages = [
    { id: 2, text: "This code is invalid.", type: "error" },
  ]
  const html = render(ui)
  assert.match(html, /name="code"/)
  assert.match(html, /<button\b(?=[^>]*name="resend")(?=[^>]*value="code")/)
  assert.match(html, /Enter the code sent by email/)
  assert.match(html, /This code is invalid/)
  assert.doesNotMatch(html, /signed in successfully/i)
})

test("stops unsupported interactions rather than dropping a required factor", () => {
  const node = input("webauthn", "submit", "webauthn")
  node.group = "webauthn"
  const html = render(form([input("csrf_token", "hidden", "token"), node]))
  assert.doesNotMatch(html, /<form/)
  assert.match(html, /not supported/i)
})

test("rejects a mismatched flow action and never renders provider scripts", () => {
  const ui = form([input("csrf_token", "hidden", "token")])
  ui.action = `${origin}/self-service/login?flow=00000000-0000-0000-0000-000000000000`
  assert.doesNotMatch(render(ui), /<form/)
  const scripted = input("method", "submit", "password", "password")
  if (scripted.attributes.node_type === "input")
    scripted.attributes.onclick = "steal()"
  assert.doesNotMatch(
    render(form([input("csrf_token", "hidden", "token"), scripted])),
    /<form|steal\(\)/
  )
})

test("code resend is available before a required code has been entered", () => {
  const html = render(
    form([
      input("csrf_token", "hidden", "token"),
      input("code", "text", undefined, "code"),
      input("resend", "submit", "code", "code"),
    ])
  )
  assert.match(html, /<button\b(?=[^>]*name="resend")(?=[^>]*formNoValidate)/)
})

test("password and code methods have separate forms with their own native CSRF", () => {
  const html = render(
    form([
      input("csrf_token", "hidden", "token"),
      input("password", "password", undefined, "password"),
      input("method", "submit", "password", "password"),
      input("identifier", "text", undefined, "code"),
      input("method", "submit", "code", "code"),
    ])
  )
  assert.equal(html.match(/<form\b/g)?.length, 2)
  assert.equal(html.match(/name="csrf_token"/g)?.length, 2)
})

test("native field patterns are preserved and unsupported option/structured values stop the form", () => {
  const field = input("code", "text", undefined, "code")
  if (field.attributes.node_type === "input")
    field.attributes.pattern = "[0-9]{6}"
  const nodes = [
    input("csrf_token", "hidden", "token"),
    field,
    input("method", "submit", "code", "code"),
  ]
  assert.match(render(form(nodes)), /pattern="\[0-9\]\{6\}"/)
  if (field.attributes.node_type === "input")
    field.attributes.options = [{ value: "one" }]
  assert.doesNotMatch(render(form(nodes)), /<form/)
  if (field.attributes.node_type === "input") {
    field.attributes.options = undefined
    field.attributes.value = { unexpected: "context" }
  }
  assert.doesNotMatch(render(form(nodes)), /<form/)
})
