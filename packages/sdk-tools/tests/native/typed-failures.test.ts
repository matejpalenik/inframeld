import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "node:http";
import { createClient, getCurrentSession } from "@inframeld/sdk";

const problem = {
  type: "about:blank",
  title: "Authentication required",
  status: 401,
  detail: "Sign in to continue",
  code: "authentication_required",
  requestId: "00000000-0000-4000-8000-000000000099",
};

for (const [name, status, body, expected] of [
  ["declared problem", 401, problem, "api"],
  ["invalid problem", 401, { title: 7 }, "decode"],
  ["undeclared error", 418, { message: "unexpected" }, "http"],
  ["invalid success", 200, null, "decode"],
] as const)
  test(`native failure distinguishes ${name}`, async () => {
    const client = createClient({
      baseUrl: "http://sdk.test",
      fetch: async () =>
        new Response(JSON.stringify(body), {
          status,
          headers: {
            "Content-Type":
              status === 200 ? "application/json" : "application/problem+json",
            "X-Request-ID": problem.requestId,
          },
        }),
    });
    const result = await getCurrentSession({ client });
    assert.ok(result.error && typeof result.error === "object");
    assert.equal(Reflect.get(result.error, "kind"), expected);
    assert.equal(result.response?.status, status);
    assert.equal(result.rawBody, JSON.stringify(body));
    assert.equal(
      result.response?.headers.get("x-request-id"),
      problem.requestId,
    );
    assert.equal(typeof Reflect.get(result.error, "message"), "string");
    if (expected === "api")
      assert.deepEqual(Reflect.get(result.error, "body"), problem);
    if (expected === "decode") assert.ok(Reflect.get(result.error, "cause"));
  });

test("network failures preserve their cause instead of pretending to be problems", async () => {
  const cause = new TypeError("network unavailable");
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async () => {
      throw cause;
    },
  });
  const result = await getCurrentSession({ client });
  assert.ok(result.error);
  assert.equal(Reflect.get(result.error, "kind"), "transport");
  assert.equal(Reflect.get(result.error, "reason"), "network");
  assert.equal(Reflect.get(result.error, "cause"), cause);
  assert.equal(result.response, undefined);
});

test("an error interceptor cannot forge a validated problem", async () => {
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async () =>
      new Response("null", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  });
  client.interceptors.error.use(() => ({ kind: "api", body: problem }));
  const result = await getCurrentSession({ client });
  assert.ok(result.error);
  assert.equal(Reflect.get(result.error, "kind"), "decode");
  assert.ok(Reflect.get(result.error, "cause"));
});

test("request construction and hook errors preserve native context", async () => {
  let count = 0;
  const invalid = createClient({
    baseUrl: "invalid URL",
    fetch: async () => {
      count++;
      return Response.json({});
    },
  });
  const construction = await getCurrentSession({ client: invalid });
  assert.equal(construction.error?.kind, "request");
  assert.equal(count, 0);
  const hookError = new Error("hook failed");
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async () =>
      new Response(JSON.stringify(problem), {
        status: 401,
        headers: { "Content-Type": "application/problem+json" },
      }),
  });
  client.interceptors.error.use(() => {
    throw hookError;
  });
  const result = await getCurrentSession({ client });
  assert.equal(result.error?.kind, "request");
  assert.ok(result.error?.kind === "request");
  assert.ok(result.error.cause instanceof AggregateError);
  assert.ok(result.error.cause.errors.includes(hookError));
  assert.deepEqual(result.error.cause.errors[0], {
    kind: "api",
    body: problem,
    message: "HTTP 401",
  });
  assert.equal(result.response?.status, 401);
  assert.equal(result.rawBody, JSON.stringify(problem));
});

test("throwing mode throws the classified failure and data-only still returns undefined", async () => {
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async () =>
      new Response(JSON.stringify(problem), {
        status: 401,
        headers: { "Content-Type": "application/problem+json" },
      }),
  });
  await assert.rejects(
    getCurrentSession({ client, throwOnError: true }),
    (error: unknown) => {
      assert.ok(error && typeof error === "object");
      assert.equal(Reflect.get(error, "kind"), "api");
      return true;
    },
  );
  const data = await getCurrentSession({ client, responseStyle: "data" });
  assert.equal(data, undefined);
});

for (const [name, status, contentType] of [
  ["incompatible representation", 200, "text/plain"],
  ["undeclared success", 201, "application/json"],
] as const)
  test(
    `body timeout on ${name} remains a transport timeout`,
    { timeout: 3000 },
    async () => {
      let count = 0;
      const server = createServer((_request, response) => {
        count++;
        response.writeHead(status, { "Content-Type": contentType });
        response.flushHeaders();
      });
      await new Promise<void>((resolve) =>
        server.listen(0, "127.0.0.1", resolve),
      );
      const address = server.address();
      assert.ok(address && typeof address === "object");
      const client = createClient({
        baseUrl: `http://127.0.0.1:${address.port}`,
        timeoutMs: 150,
      });
      try {
        const result = await getCurrentSession({ client });
        assert.ok(result.error?.kind === "transport");
        assert.equal(result.error.reason, "timeout");
        assert.equal(result.response?.status, status);
        assert.equal(count, 1);
      } finally {
        server.closeAllConnections();
        await new Promise<void>((resolve) => server.close(() => resolve()));
      }
    },
  );

test("caller cancellation cannot masquerade as the SDK deadline", async () => {
  const caller = new AbortController();
  const cause = new DOMException("Caller-owned deadline", "TimeoutError");
  caller.abort(cause);
  const client = createClient({
    baseUrl: "http://sdk.test",
    timeoutMs: 500,
    fetch: async (input) => {
      assert.ok(input instanceof Request);
      input.signal.throwIfAborted();
      return Response.json({});
    },
  });
  const result = await getCurrentSession({ client, signal: caller.signal });
  assert.ok(result.error?.kind === "transport");
  assert.equal(result.error.reason, "aborted");
  assert.equal(result.error.cause, cause);
});
