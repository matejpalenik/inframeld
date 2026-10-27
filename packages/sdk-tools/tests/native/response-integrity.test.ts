import assert from "node:assert/strict";
import test from "node:test";
import { createClient, getCurrentSession } from "@inframeld/sdk";

for (const [name, status, body, headers] of [
  [
    "empty JSON",
    200,
    "",
    { "Content-Type": "application/json", "Content-Length": "0" },
  ],
  [
    "undeclared empty status",
    204,
    null,
    { "Content-Type": "application/json" },
  ],
  [
    "incompatible representation",
    200,
    "not-a-session",
    { "Content-Type": "text/plain" },
  ],
  [
    "undeclared object status",
    201,
    '{"principalId":"00000000-0000-4000-8000-000000000001"}',
    { "Content-Type": "application/json" },
  ],
] as const) {
  test(`session rejects ${name} with inspectable HTTP context`, async () => {
    const client = createClient({
      baseUrl: "http://sdk.test",
      fetch: async () => new Response(body, { status, headers }),
    });
    const result = await getCurrentSession({
      client,
      responseStyle: "fields",
      throwOnError: false,
    });
    assert.ok(
      Object.hasOwn(result, "error"),
      "Invalid response must not become a typed success",
    );
    assert.equal(result.response?.status, status);
    assert.equal(result.rawBody, body ?? "");
  });
}

for (const contentType of ["application/json; charset=utf-8", undefined]) {
  test(`session validates declared JSON with ${String(contentType)}`, async () => {
    const client = createClient({
      baseUrl: "http://sdk.test",
      fetch: async () => {
        const response = new Response(
          '{"principalId":"00000000-0000-4000-8000-000000000001"}',
          { status: 200 },
        );
        if (contentType) response.headers.set("Content-Type", contentType);
        else response.headers.delete("Content-Type");
        return response;
      },
    });
    const result = await getCurrentSession({
      client,
      responseStyle: "fields",
      throwOnError: false,
    });
    assert.equal(
      result.data?.principalId,
      "00000000-0000-4000-8000-000000000001",
    );
  });
}

test("a valid JSON body cannot bypass declared representation through a text content type", async () => {
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async () =>
      new Response('{"principalId":"00000000-0000-4000-8000-000000000001"}', {
        headers: { "Content-Type": "text/plain" },
      }),
  });
  const result = await getCurrentSession({
    client,
    responseStyle: "fields",
    throwOnError: false,
  });
  assert.ok(result.error);
  assert.ok(result.rawBody);
});

test("generated JSON validation and response selection cannot be disabled through extra call options", async () => {
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async () => Response.json(null),
  });
  const options = Object.assign(
    { client, responseStyle: "fields" as const, throwOnError: false as const },
    { responseContract: undefined, responseValidator: undefined },
  );
  const result = await getCurrentSession(options);
  assert.ok(
    Object.hasOwn(result, "error"),
    "Generated operation must retain its validation contract",
  );
});
