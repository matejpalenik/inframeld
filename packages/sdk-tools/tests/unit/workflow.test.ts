import assert from "node:assert/strict";
import test from "node:test";
import { stage, type Stage } from "../../src/workflows/stages.ts";
import { argumentsFor } from "../../src/arguments.ts";

test("a failed SDK stage cannot prevent independent checks from running", async () => {
  const stages: Stage[] = [];
  const visited: string[] = [];
  for (const language of ["rust", "python"])
    await stage(stages, language, async () => {
      visited.push(language);
      if (language === "rust") throw new Error("compile failed");
    });
  assert.deepEqual(visited, ["rust", "python"]);
  assert.deepEqual(
    stages.map((entry) => entry.status),
    ["failed", "passed"],
  );
});
test("local filters are explicit, validated and forbidden on full verification", () => {
  assert.deepEqual(
    argumentsFor([
      "test",
      "--profile",
      "python-sync",
      "--case",
      "consent-decide",
    ]).selected,
    ["python"],
  );
  assert.equal(
    argumentsFor(["test", "--profile", "python-sync"]).partial,
    true,
  );
  for (const argv of [
    ["verify", "--case", "health"],
    ["test", "rust", "--profile", "python-sync"],
    ["test", "rust", "rust"],
    ["test", "other"],
  ])
    assert.throws(() => argumentsFor(argv));
});
