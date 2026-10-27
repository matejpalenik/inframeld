import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { snapshot } from "../../src/system/files.ts";

test("drift detection sees changed bytes and unexpected files", async () => {
  const directory = await mkdtemp(join(tmpdir(), "sdk-drift-"));
  try {
    await writeFile(join(directory, "client.rs"), "before");
    const before = await snapshot(directory);
    await writeFile(join(directory, "client.rs"), "after");
    assert.notDeepEqual(await snapshot(directory), before);
    const changed = await snapshot(directory);
    await writeFile(join(directory, "unexpected.rs"), "stale");
    assert.notDeepEqual(await snapshot(directory), changed);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
