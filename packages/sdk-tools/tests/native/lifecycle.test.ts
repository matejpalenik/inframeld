import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";
import { execute } from "../../drivers/typescript.ts";
import type { DriverRequest } from "../../src/conformance/protocol.ts";

test("cancelling an active native Fetch call permits a subsequent client request", async () => {
  let dispatches = 0;
  let entered: (() => void) | undefined;
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const server = createServer((_request, response) => {
    dispatches++;
    if (dispatches === 1) entered?.();
    else response.end(JSON.stringify({ status: "ok" }));
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  const request: DriverRequest = {
    version: 2,
    profile: "typescript-node",
    caseId: "cancel",
    baseUrl: `http://127.0.0.1:${address.port}`,
    calls: [{ id: "one", operation: "getHealth", headers: {}, timeout: 2000 }],
  };
  const controller = new AbortController();
  try {
    const active = execute(request, controller.signal);
    await started;
    controller.abort(new Error("caller cancelled"));
    const reply = await active;
    assert.equal(reply.kind, "observations");
    assert.ok(
      reply.kind === "observations" &&
        reply.observations[0]?.kind === "sdk-error",
    );
    const reused = await execute({ ...request, caseId: "after-cancel" });
    assert.ok(
      reused.kind === "observations" &&
        reused.observations[0]?.kind === "success",
    );
    assert.equal(dispatches, 2);
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});

test("the same generated client is reusable after supported operation cancellation", async () => {
  const { createClient, getHealth } = await import("@inframeld/sdk");
  let dispatches = 0;
  let entered: (() => void) | undefined;
  const started = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const client = createClient({
    baseUrl: "http://sdk.test",
    fetch: async (input, init) => {
      dispatches++;
      if (dispatches > 1) return Response.json({ status: "ok" });
      const signal = input instanceof Request ? input.signal : init?.signal;
      assert.ok(signal);
      return new Promise<Response>((_resolve, reject) => {
        signal.addEventListener("abort", () => reject(signal.reason), {
          once: true,
        });
        entered?.();
      });
    },
  });
  const controller = new AbortController();
  const active = getHealth({
    client,
    signal: controller.signal,
    throwOnError: false,
    responseStyle: "fields",
  });
  await started;
  controller.abort(new Error("cancel active SDK operation"));
  const failure = (await active).error;
  assert.ok(failure?.kind === "transport");
  assert.equal(failure.reason, "aborted");
  const reused = await getHealth({
    client,
    signal: AbortSignal.timeout(1000),
    throwOnError: false,
    responseStyle: "fields",
  });
  assert.equal(reused.data?.status, "ok");
  assert.equal(dispatches, 2);
});
