import assert from "node:assert/strict";
import test from "node:test";
import { withinDeadline } from "../../src/system/deadline.ts";

test("a stalled browser or cleanup promise cannot hang the workflow", async () => {
  await assert.rejects(withinDeadline(new Promise(() => {}), 20), /deadline/);
  assert.equal(await withinDeadline(Promise.resolve("closed"), 100), "closed");
});
