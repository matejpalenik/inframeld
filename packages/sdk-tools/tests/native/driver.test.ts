import assert from "node:assert/strict";
import test from "node:test";
import { execute } from "../../drivers/typescript.ts";

test("the TypeScript driver rejects another runtime profile before SDK invocation", async () => {
  await assert.rejects(
    execute({
      version: 2,
      profile: "rust",
      caseId: "wrong",
      baseUrl: "http://sdk.invalid",
      calls: [{ id: "one", operation: "getHealth", headers: {}, timeout: 1 }],
    }),
    /profile/i,
  );
});
