/** A rejected subprocess must not retain local handles and prevent CLI exit. */
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { command } from "../../../src/system/process.ts";

const marker = process.argv[2];
assert.ok(marker);
const controller = new AbortController();
const running = command(
  process.execPath,
  [
    "-e",
    "require('node:fs').writeFileSync(process.argv[1],String(process.pid));setInterval(()=>{},1000)",
    marker,
  ],
  { signal: controller.signal, cleanupTimeout: 20 },
);
void running.catch(() => {});
let pid: number | undefined;
for (let attempt = 0; attempt < 100; attempt++) {
  try {
    pid = Number(await readFile(marker, "utf8"));
    break;
  } catch {
    await new Promise((resolve) => setTimeout(resolve, 10));
  }
}
assert.ok(pid);
const original = process.kill.bind(process);
process.kill = (target: number, signal?: NodeJS.Signals | number) => {
  if (target === -pid && signal !== 0)
    throw Object.assign(new Error("termination denied"), { code: "EPERM" });
  return original(target, signal);
};
try {
  controller.abort(new Error("expected fixture cancellation"));
  await running;
  throw new Error("Denied cleanup must fail");
} catch (error) {
  console.error(String(error));
  process.exitCode = 1;
} finally {
  process.kill = original;
}
