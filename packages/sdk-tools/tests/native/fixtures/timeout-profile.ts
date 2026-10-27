/** Deliberately stall a real profile so its parent can qualify forced cleanup. */
import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { cache } from "../../../src/config.ts";
import { startProfile } from "../../../src/conformance/profile.ts";
import { installInterruptHandlers } from "../../../src/system/shutdown.ts";

process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(cache, "browsers");
const { chromium } = await import("playwright");
installInterruptHandlers();

test("deliberately stalled profile", async (context) => {
  const work = process.env.SDK_TIMEOUT_WORK;
  assert.ok(work);
  const launch = chromium.launchServer.bind(chromium);
  let browserPid: number | undefined;
  context.mock.method(
    chromium,
    "launchServer",
    async (options: Parameters<typeof chromium.launchServer>[0]) => {
      const owned = await launch(options);
      browserPid = owned.process().pid;
      context.mock.method(owned, "close", () => new Promise<void>(() => {}));
      return owned;
    },
  );
  await writeFile(join(work, "driver.mjs"), "export const bindings=[];");
  const fixture = await startProfile(
    "typescript-chromium",
    { bindings: [], typescriptBundle: join(work, "driver.mjs") },
    work,
  );
  await writeFile(
    join(work, "ready.json"),
    JSON.stringify({ browser: browserPid, backend: fixture.backend.pid }),
  );
  await new Promise<void>(() => {});
});
