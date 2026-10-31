/** Denied production cleanup fails promptly, while an independent sole waiter reaps the fuse. */
import assert from "node:assert/strict";
import { readFile, writeFile, rm } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { withResources } from "../../../src/system/process.ts";
import { withinDeadline } from "../../../src/system/deadline.ts";
import { fixtureDiagnostic } from "./fixture-diagnostics.ts";

/** Await the independent waiter's receipt. This never qualifies denied production cleanup. */
export async function withDeniedFixtureRecovery(
  work: string,
  deadline: number,
  assertions: () => Promise<void>,
  readReceipt: () => Promise<unknown> = async () =>
    JSON.parse(await readFile(join(work, "fixture-recovered.json"), "utf8")),
): Promise<void> {
  await withResources(assertions, async () => {
    const recoveryDeadline = Math.min(deadline, performance.now() + 6000);
    let recovered = false;
    let failure: unknown;
    while (performance.now() < recoveryDeadline) {
      try {
        const receipt = await withinDeadline(
          readReceipt(),
          Math.max(0, recoveryDeadline - performance.now()),
        );
        if (performance.now() >= recoveryDeadline) break;
        if (
          !receipt ||
          typeof receipt !== "object" ||
          (receipt as { reaped?: unknown }).reaped !== true
        )
          throw new Error("Invalid independent fixture recovery receipt");
        recovered = true;
        break;
      } catch (error) {
        failure = error;
      }
      await new Promise((resolve) =>
        setTimeout(
          resolve,
          Math.min(25, Math.max(0, recoveryDeadline - performance.now())),
        ),
      );
    }
    if (!recovered) {
      process.stderr.write(
        fixtureDiagnostic({
          phase: "fixture-terminal",
          category: "owner-unknown",
          status: null,
        }),
      );
      throw new Error("Independent fixture cleanup remained unresolved", {
        cause: failure,
      });
    }
    await rm(work, { recursive: true, force: true });
  });
}

async function runDeniedFixture(marker: string): Promise<void> {
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
  const running = controlled.command(
    "python3",
    ["-B", fixture, "wait", marker],
    {
      signal: controller.signal,
      cleanupTimeout: 20,
    },
  );
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
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  assert.ok(process.argv[2]);
  await runDeniedFixture(process.argv[2]);
}
