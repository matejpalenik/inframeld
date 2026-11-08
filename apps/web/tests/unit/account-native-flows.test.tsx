import assert from "node:assert/strict"
import { test } from "node:test"
import { JSDOM } from "jsdom"
import { renderToStaticMarkup } from "react-dom/server"
import type {
  UiContainer,
  UiNode,
  UiNodeInputAttributes,
} from "@ory/client-fetch"
import { KratosFlowForm } from "../../components/account/kratos-flow-form"
import type { AccountFlowKind } from "../../lib/account/kratos"

const origin = "https://inframeld.account.test:8443"
const id = "c1fab4f4-ffce-4e5a-ae73-25cbff832764"

function input(
  name: string,
  type: UiNodeInputAttributes["type"],
  value: string,
  group: UiNode["group"] = "default"
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

function render(
  kind: AccountFlowKind,
  nodes: UiNode[],
  action?: string
): string {
  const ui: UiContainer = {
    action: action ?? `${origin}/self-service/${kind}?flow=${id}`,
    method: "POST",
    nodes: [input("csrf_token", "hidden", "native-csrf"), ...nodes],
  }
  return renderToStaticMarkup(
    <KratosFlowForm ui={ui} flowId={id} flowKind={kind} publicOrigin={origin} />
  )
}

const verificationAnchor = {
  type: "a",
  group: "code",
  attributes: {
    node_type: "a",
    id: "continue",
    href: `${origin}/`,
    title: { id: 1, text: "Continue", type: "info" },
  },
  messages: [],
  meta: { label: { id: 1, text: "Continue", type: "info" } },
} satisfies UiNode

const verificationCompletion: UiContainer = {
  action: `${origin}/`,
  method: "GET",
  messages: [
    {
      id: 1080001,
      type: "success",
      text: "You successfully verified your email address.",
    },
  ],
  nodes: [input("csrf_token", "hidden", "native-csrf"), verificationAnchor],
}

test("verification completion renders the native success and checked Continue without a form", () => {
  const dom = new JSDOM(
    renderToStaticMarkup(
      <KratosFlowForm
        ui={verificationCompletion}
        flowId={id}
        flowKind="verification"
        publicOrigin={origin}
        verificationState="passed_challenge"
      />
    )
  )
  try {
    const document = dom.window.document
    assert.equal(
      document.querySelector('[role="status"]')?.textContent,
      "You successfully verified your email address."
    )
    const link = document.querySelector<HTMLAnchorElement>("a")!
    assert.equal(link.textContent, "Continue")
    assert.equal(link.href, `${origin}/`)
    assert.equal(
      document.querySelector('form, input, button, [role="alert"]'),
      null
    )
  } finally {
    dom.window.close()
  }
})

for (const [name, ui] of [
  ...[
    ["external", "https://outside.test/"],
    ["insecure", "http://inframeld.account.test:8443/"],
    ["script", "javascript:alert(1)"],
    ["credentials", "https://user@inframeld.account.test:8443/"],
    ["unsupported-path", `${origin}/settings`],
    ["query", `${origin}/?return_to=outside`],
    ["fragment", `${origin}/#outside`],
  ].map(([name, target]): [string, UiContainer] => [
    name,
    {
      ...verificationCompletion,
      action: target,
      nodes: [
        {
          ...verificationAnchor,
          attributes: {
            ...verificationAnchor.attributes,
            href: target,
          },
        },
      ],
    },
  ]),
  ["method", { ...verificationCompletion, method: "POST" }],
  ["missing-anchor", { ...verificationCompletion, nodes: [] }],
  [
    "duplicate-anchor",
    {
      ...verificationCompletion,
      nodes: [...verificationCompletion.nodes, verificationAnchor],
    },
  ],
  [
    "mismatched-anchor",
    {
      ...verificationCompletion,
      nodes: [
        {
          ...verificationAnchor,
          attributes: {
            ...verificationAnchor.attributes,
            href: `${origin}/settings`,
          },
        },
      ],
    },
  ],
  [
    "wrong-anchor-group",
    {
      ...verificationCompletion,
      nodes: [{ ...verificationAnchor, group: "default" }],
    },
  ],
  [
    "wrong-anchor-id",
    {
      ...verificationCompletion,
      nodes: [
        {
          ...verificationAnchor,
          attributes: {
            ...verificationAnchor.attributes,
            id: "other",
          },
        },
      ],
    },
  ],
] satisfies readonly (readonly [string, UiContainer])[]) {
  test(`verification completion replaces unsafe ${name} continuation with Account navigation`, () => {
    const html = renderToStaticMarkup(
      <KratosFlowForm
        ui={ui}
        flowId={id}
        flowKind="verification"
        publicOrigin={origin}
        verificationState="passed_challenge"
      />
    )
    const dom = new JSDOM(html)
    try {
      const document = dom.window.document
      assert.equal(
        document.querySelector('[role="status"]')?.textContent,
        "You successfully verified your email address."
      )
      const link = document.querySelector("a")!
      assert.equal(link.textContent, "Account")
      assert.equal(link.getAttribute("href"), "/")
      assert.equal(
        document.querySelector('form, input, button, [role="alert"]'),
        null
      )
    } finally {
      dom.window.close()
    }
  })
}

test("verification completion cannot turn an unfinished verification GET into a form or success", () => {
  const html = renderToStaticMarkup(
    <KratosFlowForm
      ui={verificationCompletion}
      flowId={id}
      flowKind="verification"
      publicOrigin={origin}
    />
  )
  assert.match(html, /could not be verified/)
  assert.doesNotMatch(html, /successfully verified|Continue|<form/)
})

for (const kind of ["registration", "recovery", "settings", "login"] as const) {
  test(`verification completion does not bypass ${kind} form guards`, () => {
    const html = renderToStaticMarkup(
      <KratosFlowForm
        ui={verificationCompletion}
        flowId={id}
        flowKind={kind}
        publicOrigin={origin}
        verificationState="passed_challenge"
      />
    )
    assert.match(html, /could not be verified/)
    assert.doesNotMatch(html, /successfully verified|Continue|<form/)
  })
}

for (const kind of [
  "registration",
  "verification",
  "recovery",
  "settings",
] as const) {
  test(`renders ${kind} only to its native endpoint with actual method and CSRF`, () => {
    const method =
      kind === "verification" || kind === "recovery" ? "code" : "password"
    const html = render(kind, [
      input(
        kind === "settings" ? "password" : "traits.email",
        kind === "settings" ? "password" : "email",
        "",
        method
      ),
      input("method", "submit", method, method),
    ])
    assert.match(
      html,
      new RegExp(`action="${origin}/self-service/${kind}\\?flow=${id}"`)
    )
    assert.match(html, /name="csrf_token"[^>]*value="native-csrf"/)
    assert.match(
      html,
      new RegExp(`<button\\b(?=[^>]*name="method")(?=[^>]*value="${method}")`)
    )
  })
}

for (const method of ["totp", "lookup_secret"] as const) {
  test(`preserves the configured ${method} required input and native submit value`, () => {
    const field = method === "totp" ? "totp_code" : "lookup_secret"
    const html = render("login", [
      input(field, "text", "", method),
      input("method", "submit", method, method),
    ])
    assert.match(
      html,
      new RegExp(`<input\\b(?=[^>]*name="${field}")(?=[^>]*required)`)
    )
    assert.match(
      html,
      new RegExp(`<button\\b(?=[^>]*name="method")(?=[^>]*value="${method}")`)
    )
  })
}

test("preserves the configured native OIDC provider submit button", () => {
  const html = render("login", [input("provider", "submit", "company", "oidc")])
  assert.match(
    html,
    /<button\b(?=[^>]*name="provider")(?=[^>]*value="company")/
  )
})

test("native profile-first registration collects required traits before credential selection", () => {
  const dom = new JSDOM(
    render("registration", [
      input("traits.email", "email", "", "default"),
      input("method", "submit", "profile", "profile"),
    ])
  )
  try {
    const document = dom.window.document
    assert.equal(document.querySelector("h2")!.textContent, "Account details")
    const button = document.querySelector<HTMLButtonElement>(
      'button[name="method"]'
    )!
    const form = button.form!
    assert.equal(form.action, `${origin}/self-service/registration?flow=${id}`)
    assert.equal(form.method, "post")
    assert.equal(button.value, "profile")
    assert.equal(button.formNoValidate, false)
    const email = form.querySelector<HTMLInputElement>('[name="traits.email"]')!
    assert.equal(email.required, true)
    assert.equal(form.checkValidity(), false)
    email.value = "alice@example.test"
    assert.equal(form.checkValidity(), true)
    assert.equal(
      form.querySelector<HTMLInputElement>('[name="csrf_token"]')!.value,
      "native-csrf"
    )
    assert.equal(document.querySelector('[name="password"]'), null)
  } finally {
    dom.window.close()
  }
})

test("native credential selection preserves hidden profile traits and the previous-screen submit", () => {
  const dom = new JSDOM(
    render("registration", [
      input("traits.email", "hidden", "alice@example.test", "default"),
      input("screen", "submit", "previous", "profile"),
      input("password", "password", "", "password"),
      input("method", "submit", "password", "password"),
    ])
  )
  try {
    const document = dom.window.document
    const back = document.querySelector<HTMLButtonElement>(
      'button[name="screen"]'
    )!
    assert.equal(back.value, "previous")
    const password =
      document.querySelector<HTMLInputElement>('[name="password"]')!
    assert.equal(password.required, true)
    assert.equal(password.form!.checkValidity(), false)
    const submit = password.form!.querySelector<HTMLButtonElement>(
      'button[name="method"]'
    )!
    assert.equal(submit.value, "password")
    assert.equal(submit.formNoValidate, false)
    for (const form of [back.form!, password.form!]) {
      const email = form.querySelector<HTMLInputElement>(
        '[name="traits.email"]'
      )!
      assert.equal(email.type, "hidden")
      assert.equal(email.value, "alice@example.test")
      assert.equal(
        form.querySelector<HTMLInputElement>('[name="csrf_token"]')!.value,
        "native-csrf"
      )
      assert.equal(
        form.action,
        `${origin}/self-service/registration?flow=${id}`
      )
    }
  } finally {
    dom.window.close()
  }
})

for (const kind of ["login", "registration"] as const) {
  test(`native OIDC ${kind} selection can submit before unrelated required profile fields`, () => {
    const dom = new JSDOM(
      render(kind, [
        input("traits.email", "email", "", "default"),
        input("password", "password", "", "password"),
        input("method", "submit", "password", "password"),
        input("provider", "submit", "company", "oidc"),
      ])
    )
    try {
      const document = dom.window.document
      const provider = document.querySelector<HTMLButtonElement>(
        'button[name="provider"]'
      )!
      const form = provider.form!
      assert.equal(form.checkValidity(), false)
      assert.equal(form.noValidate, false)
      assert.equal(provider.formNoValidate, true)
      assert.equal(form.action, `${origin}/self-service/${kind}?flow=${id}`)
      assert.equal(form.method, "post")
      assert.equal(
        form.querySelector<HTMLInputElement>('[name="csrf_token"]')!.value,
        "native-csrf"
      )
      assert.equal(provider.value, "company")
      assert.equal(
        document.querySelector<HTMLButtonElement>('button[name="method"]')!
          .formNoValidate,
        false
      )
    } finally {
      dom.window.close()
    }
  })
}

for (const [kind, group, name, value] of [
  ["login", "password", "method", "password"],
  ["login", "code", "method", "code"],
  ["login", "totp", "method", "totp"],
  ["login", "lookup_secret", "method", "lookup_secret"],
  ["registration", "password", "provider", "company"],
  ["registration", "oidc", "provider", ""],
  ["settings", "oidc", "provider", "company"],
] as const) {
  test(`${kind} ${group}/${name}/${value || "empty"} keeps ordinary required-field validation`, () => {
    const dom = new JSDOM(
      render(kind, [
        input("traits.email", "email", "", "default"),
        input(name, "submit", value, group),
      ])
    )
    try {
      const button =
        dom.window.document.querySelector<HTMLButtonElement>("button")!
      assert.equal(button.form!.checkValidity(), false)
      assert.equal(button.form!.noValidate, false)
      assert.equal(button.formNoValidate, false)
    } finally {
      dom.window.close()
    }
  })
}

test("renders the current native TOTP QR and secret without exposing other context", () => {
  const html = render("settings", [
    {
      type: "img",
      group: "totp",
      attributes: {
        node_type: "img",
        id: "totp_qr",
        src: "data:image/png;base64,iVBORw0KGgo=",
        width: 256,
        height: 256,
      },
      messages: [],
      meta: {
        label: { id: 1, type: "info", text: "Authenticator app QR code" },
      },
    },
    {
      type: "text",
      group: "totp",
      attributes: {
        node_type: "text",
        id: "totp_secret_key",
        text: {
          id: 1,
          type: "info",
          text: "CURRENT-ENROLLMENT-SECRET",
          context: { privateProviderConfig: "MUST-NOT-RENDER" },
        },
      },
      messages: [],
      meta: {
        label: { id: 1, type: "info", text: "Authenticator app secret" },
      },
    },
    input("totp_code", "text", "", "totp"),
    input("method", "submit", "totp", "totp"),
  ])
  assert.match(html, /<img[^>]*alt="Authenticator app QR code"/)
  assert.match(html, /data:image\/png;base64,iVBORw0KGgo=/)
  assert.match(html, /CURRENT-ENROLLMENT-SECRET/)
  assert.doesNotMatch(html, /MUST-NOT-RENDER/)
})

test("renders native lookup codes as text and preserves each provider action", () => {
  const html = render("settings", [
    {
      type: "text",
      group: "lookup_secret",
      attributes: {
        node_type: "text",
        id: "lookup_secret_codes",
        text: { id: 1, type: "info", text: "first-code, used, third-code" },
      },
      messages: [],
      meta: {
        label: { id: 1, type: "info", text: "Keep your backup codes safe" },
      },
    },
    ...["reveal", "regenerate", "confirm", "disable"].map((action) =>
      input(`lookup_secret_${action}`, "submit", "true", "lookup_secret")
    ),
  ])
  assert.match(html, /first-code, used, third-code/)
  for (const action of ["reveal", "regenerate", "confirm", "disable"])
    assert.match(
      html,
      new RegExp(
        `<button\\b(?=[^>]*name="lookup_secret_${action}")(?=[^>]*value="true")`
      )
    )
})

test("rejects external or non-PNG enrollment images without rendering partial forms", () => {
  for (const src of [
    "https://outside.test/track",
    "data:image/svg+xml;base64,PHN2Zz4=",
    "javascript:alert(1)",
  ]) {
    const html = render("settings", [
      {
        type: "img",
        group: "totp",
        attributes: {
          node_type: "img",
          id: "totp_qr",
          src,
          width: 256,
          height: 256,
        },
        messages: [],
        meta: {},
      },
      input("method", "submit", "totp", "totp"),
    ])
    assert.doesNotMatch(html, /<form|<img|outside\.test|javascript:/)
  }
})

test("a selected flow cannot submit another account operation", () => {
  const html = render(
    "registration",
    [input("method", "submit", "password", "password")],
    `${origin}/self-service/settings?flow=${id}`
  )
  assert.doesNotMatch(html, /<form/)
})
