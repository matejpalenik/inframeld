import assert from "node:assert/strict";
import { sdkTest } from "../../src/conformance/cases.ts";
import {
  assertSuccess,
  assertJsonBody,
} from "../../src/conformance/assertions.ts";

const cookie = { Cookie: "ory_kratos_session=sdk-cookie" };

sdkTest(
  {
    id: "consent-default-omitted",
    operation: "decideHumanOAuthConsent",
    outcome: "success",
  },
  async ({ call, origin }) => {
    const input = { consentChallenge: "a+b&/", decision: "allow" };
    const { observation, witness } = await call({
      operation: "decideHumanOAuthConsent",
      headers: { ...cookie, Origin: origin, "X-Inframeld-CSRF": "1" },
      body: input,
      timeout: 2000,
    });
    assert.equal(
      assertSuccess(observation, 200).redirectTo,
      "https://auth.test/continue",
    );
    assertJsonBody(witness, input);
  },
);

sdkTest(
  {
    id: "consent-inspect",
    operation: "inspectHumanOAuthConsent",
    outcome: "success",
  },
  async ({ call }) => {
    const { observation, witness } = await call({
      operation: "inspectHumanOAuthConsent",
      headers: cookie,
      query: { consent_challenge: "a+b&/" },
      timeout: 2000,
    });
    const body = assertSuccess(observation, 200);
    assert.equal(body.accountSubject, "alice");
    assert.equal(body.clientId, "inframeld-cli");
    assert.deepEqual(body.requestedScopes, ["inframeld:api"]);
    assert.equal(
      new URLSearchParams(String(witness.query)).get("consent_challenge"),
      "a+b&/",
    );
  },
);

sdkTest(
  {
    id: "consent-decide",
    operation: "decideHumanOAuthConsent",
    outcome: "success",
  },
  async ({ call, origin }) => {
    const input = {
      consentChallenge: "a+b&/",
      decision: "allow",
      remember: true,
    };
    const { observation, witness } = await call({
      operation: "decideHumanOAuthConsent",
      headers: { ...cookie, Origin: origin, "X-Inframeld-CSRF": "1" },
      body: input,
      timeout: 2000,
    });
    assert.equal(
      assertSuccess(observation, 200).redirectTo,
      "https://auth.test/continue",
    );
    assertJsonBody(witness, input);
    assert.equal(witness.origin, origin);
    assert.equal(witness.csrf, "1");
  },
);

sdkTest(
  {
    id: "consent-csrf-denied",
    operation: "decideHumanOAuthConsent",
    outcome: "failure",
  },
  async ({ call }) => {
    const { observation } = await call({
      operation: "decideHumanOAuthConsent",
      headers: cookie,
      body: { consentChallenge: "a+b&/", decision: "allow", remember: true },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 403);
    assert.notEqual(observation.validation, "none");
  },
);

sdkTest(
  {
    id: "consent-bearer-denied",
    operation: "decideHumanOAuthConsent",
    outcome: "failure",
  },
  async ({ call, origin }) => {
    const { observation } = await call({
      operation: "decideHumanOAuthConsent",
      headers: {
        ...cookie,
        Authorization: "Bearer sdk-human",
        Origin: origin,
        "X-Inframeld-CSRF": "1",
      },
      body: { consentChallenge: "a+b&/", decision: "allow", remember: true },
      timeout: 2000,
    });
    assert.equal(observation.kind, "sdk-error");
    assert.equal(observation.status, 400);
    assert.notEqual(observation.validation, "none");
  },
);
