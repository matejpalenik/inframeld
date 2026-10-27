import assert from "node:assert/strict";
import test from "node:test";
import { mkdir, mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { assertNoDrift } from "../../src/generation/drift.ts";

test("regeneration compares source bytes and detects changed, added and removed output", async () => {
  const work = await mkdtemp(join(tmpdir(), "sdk-drift-proof-"));
  const before = join(work, "before");
  const after = join(work, "after");
  try {
    await mkdir(before);
    await mkdir(after);
    await writeFile(join(before, "sdk.ts"), "export type Id = string;\n");
    await writeFile(join(after, "sdk.ts"), "export type Id = string;\n");
    await assertNoDrift(before, after);
    await writeFile(join(after, "sdk.ts"), "export type Id = number;\n");
    await assert.rejects(assertNoDrift(before, after), /sdk.ts/);
    await writeFile(join(after, "sdk.ts"), "export type Id = string;\n");
    await writeFile(join(after, "extra.ts"), "export {};\n");
    await assert.rejects(assertNoDrift(before, after), /extra.ts/);
    await rm(join(after, "extra.ts"));
    await rm(join(after, "sdk.ts"));
    await assert.rejects(assertNoDrift(before, after), /sdk.ts/);
  } finally {
    await rm(work, { recursive: true, force: true });
  }
});
