/** Denied production cleanup fails promptly, while an independent sole waiter reaps the fuse. */
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const marker = process.argv[2];
assert.ok(marker);
const work = dirname(marker);
const source = fileURLToPath(
  new URL("../../../src/system/process.ts", import.meta.url),
);
const owner = fileURLToPath(
  new URL("../../../src/system/process_owner.py", import.meta.url),
);
const fixture = fileURLToPath(
  new URL("../../unit/fixtures/process_tree.py", import.meta.url),
);
await writeFile(join(work, "process.mts"), await readFile(source));
await writeFile(
  join(work, "budgets.ts"),
  await readFile(new URL("../../../src/system/budgets.ts", import.meta.url)),
);
await writeFile(
  join(work, "process_owner.py"),
  [
    "import runpy, sys",
    `sys.argv = ${JSON.stringify([fixture, "denied-owner", owner, marker])}`,
    `runpy.run_path(${JSON.stringify(fixture)}, run_name='__main__')`,
  ].join("\n"),
);
const controlled: typeof import("../../../src/system/process.ts") =
  await import(pathToFileURL(join(work, "process.mts")).href);
const controller = new AbortController();
const running = controlled.command("python3", ["-B", fixture, "wait", marker], {
  signal: controller.signal,
  cleanupTimeout: 20,
});
void running.catch(() => {});
const deadline = performance.now() + 1000;
while (performance.now() < deadline) {
  try {
    await readFile(marker);
    break;
  } catch {
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}
await readFile(marker);
try {
  controller.abort(new Error("expected fixture cancellation"));
  await running;
  throw new Error("Denied cleanup must fail");
} catch (error) {
  assert.ok(error instanceof AggregateError);
  assert.match(String(error.errors[0]), /expected fixture cancellation/);
  assert.match(String(error.errors[1]), /cleanup/i);
  await writeFile(
    join(work, "failure.json"),
    JSON.stringify({
      primary: String(error.errors[0]),
      cleanup: String(error.errors[1]),
    }),
  );
  console.error(error);
  process.exitCode = 1;
}
