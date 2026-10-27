import assert from "node:assert/strict";
import { createServer } from "node:http";
import test from "node:test";
import { controlJson } from "../../src/conformance/backend.ts";

test("a stalled control response has a deadline and does not hang readiness", async () => {
  const server = createServer(() => {});
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  try {
    await assert.rejects(
      controlJson(`http://127.0.0.1:${address.port}`, {}, 50),
      /timeout/i,
    );
  } finally {
    server.closeAllConnections();
    await new Promise<void>((resolve) => server.close(() => resolve()));
  }
});
