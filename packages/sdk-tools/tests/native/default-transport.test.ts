import assert from "node:assert/strict";
import test from "node:test";
import { createServer } from "node:http";
import { setTimeout as delay } from "node:timers/promises";
import { createClient, getHealth } from "@inframeld/sdk";

test(
  "the default deadline remains active when the caller supplies cancellation",
  { timeout: 9000 },
  async () => {
    let count = 0;
    const server = createServer(() => {
      count++;
    });
    await new Promise<void>((resolve) =>
      server.listen(0, "127.0.0.1", resolve),
    );
    const address = server.address();
    assert.ok(address && typeof address === "object");
    const client = createClient({
      baseUrl: `http://127.0.0.1:${address.port}`,
    });
    const controller = new AbortController();
    const watchdog = setTimeout(
      () => controller.abort(new Error("Test watchdog")),
      8000,
    );
    const started = performance.now();
    try {
      const result = await getHealth({ client, signal: controller.signal });
      assert.equal(result.error?.kind, "transport");
      assert.ok(result.error?.kind === "transport");
      assert.equal(result.error.reason, "timeout");
      assert.ok(performance.now() - started >= 4500);
      assert.ok(performance.now() - started < 8000);
      assert.equal(count, 1);
      assert.equal(controller.signal.aborted, false);
    } finally {
      clearTimeout(watchdog);
      server.closeAllConnections();
      await new Promise<void>((resolve) => server.close(() => resolve()));
    }
  },
);

test("default requests do not follow redirects", async () => {
  let count = 0;
  const server = createServer((request, response) => {
    count++;
    if (request.url === "/health")
      response.writeHead(307, { Location: "/target" }).end();
    else
      response
        .writeHead(200, { "Content-Type": "application/json" })
        .end('{"status":"ok"}');
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const client = createClient({ baseUrl: `http://127.0.0.1:${address.port}` });
  try {
    assert.equal((await getHealth({ client })).response?.status, 307);
    assert.equal(count, 1);
    assert.equal(
      (await getHealth({ client, redirect: "follow" })).data?.status,
      "ok",
    );
    assert.equal(count, 3);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("request timeout overrides client timeout and preserves reuse", async () => {
  let count = 0;
  const client = createClient({
    baseUrl: "http://sdk.test",
    timeoutMs: 20,
    fetch: async (input) => {
      count++;
      assert.ok(input instanceof Request);
      await delay(60, undefined, { signal: input.signal });
      return Response.json({ status: "ok" });
    },
  });
  assert.equal((await getHealth({ client })).error?.kind, "transport");
  assert.equal(
    (await getHealth({ client, timeoutMs: undefined })).error?.kind,
    "transport",
  );
  assert.equal(
    (await getHealth({ client, timeoutMs: 500 })).data?.status,
    "ok",
  );
  assert.equal(count, 3);
});

test("invalid timeout configuration fails before dispatch", async () => {
  let count = 0;
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async () => {
      count++;
      return Response.json({ status: "ok" });
    },
  });
  for (const timeoutMs of [0, -1, Number.NaN, Number.POSITIVE_INFINITY]) {
    const result = await getHealth({ client, timeoutMs });
    assert.equal(result.error?.kind, "request");
  }
  assert.equal(count, 0);
});

test("JavaScript callers cannot turn invalid timeout values into defaults", async () => {
  let count = 0;
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async () => {
      count++;
      return Response.json({ status: "ok" });
    },
  });
  for (const timeoutMs of [null, "5000", {}]) {
    const dynamic: Record<string, unknown> = { timeoutMs };
    const result = await getHealth(Object.assign({ client }, dynamic));
    assert.equal(result.error?.kind, "request");
  }
  assert.equal(count, 0);
});
