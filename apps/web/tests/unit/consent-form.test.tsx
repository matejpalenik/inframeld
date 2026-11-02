import assert from "node:assert/strict"
import { test } from "node:test"
import { renderToStaticMarkup } from "react-dom/server"
import { ConsentForm } from "../../app/(account)/consent/consent-form"

const origin = "https://inframeld.account.test:8443"
const props = {
  challenge: "private-challenge",
  publicOrigin: origin,
  hydraOrigin: "https://hydra.account.test:8443",
}

test("displays the checked account and installation with explicit allow and cancel controls", () => {
  const html = renderToStaticMarkup(
    <ConsentForm
      {...props}
      initialView={{
        kind: "ready",
        details: {
          accountSubject: "alice-id",
          installation: origin,
          clientId: "inframeld-cli",
          requestedScopes: ["openid", "inframeld:api"],
          requestedAudience: [origin],
          approvalRequired: true,
          rememberConsentSeconds: 3600,
        },
      }}
    />
  )
  assert.match(html, /alice-id/)
  assert.match(html, /https:\/\/inframeld.account.test:8443/)
  assert.match(html, /Allow CLI access/)
  assert.match(html, /Cancel/)
  assert.doesNotMatch(html, /checked=""|private-challenge|token acquired/i)
})

test("a stopped inspection shows no protected account or approval controls", () => {
  const html = renderToStaticMarkup(
    <ConsentForm
      {...props}
      initialView={{
        kind: "stopped",
        message: "Your session expired. Restart from the client.",
      }}
    />
  )
  assert.match(html, /Your session expired/)
  assert.doesNotMatch(html, /Allow CLI access|alice-id/)
})
