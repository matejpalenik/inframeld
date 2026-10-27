/** Actual Chromium ownership under startup interruption and failed graceful close. */
import assert from "node:assert/strict";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import type { BrowserServer } from "playwright";
import { cache } from "../../src/config.ts";
import { startProfile } from "../../src/conformance/profile.ts";

process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(cache, "browsers");
const { chromium } = await import("playwright");

test(
  "startup cancellation closes a browser acquired before the fixture returns",
  { timeout: 30_000 },
  async (context) => {
    const work = await mkdtemp(join(tmpdir(), "sdk-startup-cancel-"));
    const controller = new AbortController();
    let owned: BrowserServer | undefined;
    const launch = chromium.launchServer.bind(chromium);
    context.mock.method(
      chromium,
      "launchServer",
      async (options: Parameters<typeof chromium.launchServer>[0]) => {
        owned = await launch(options);
        controller.abort(new Error("cancel startup after browser allocation"));
        return owned;
      },
    );
    try {
      await writeFile(join(work, "driver.mjs"), "export const bindings=[];");
      await assert.rejects(
        startProfile(
          "typescript-chromium",
          { bindings: [], typescriptBundle: join(work, "driver.mjs") },
          work,
          controller.signal,
        ),
        /cancel startup/,
      );
      assert.ok(owned);
      assert.ok(
        owned.process().exitCode !== null ||
          owned.process().signalCode !== null,
      );
    } finally {
      await owned?.kill();
      await rm(work, { recursive: true, force: true });
    }
  },
);

test(
  "a stalled browser close is force-killed and remains a cleanup failure",
  { timeout: 30_000 },
  async (context) => {
    const work = await mkdtemp(join(tmpdir(), "sdk-browser-kill-"));
    let owned: BrowserServer | undefined;
    const launch = chromium.launchServer.bind(chromium);
    context.mock.method(
      chromium,
      "launchServer",
      async (options: Parameters<typeof chromium.launchServer>[0]) => {
        owned = await launch(options);
        context.mock.method(owned, "close", () => new Promise<void>(() => {}));
        return owned;
      },
    );
    try {
      await writeFile(join(work, "driver.mjs"), "export const bindings=[];");
      const fixture = await startProfile(
        "typescript-chromium",
        { bindings: [], typescriptBundle: join(work, "driver.mjs") },
        work,
      );
      await assert.rejects(fixture.close(), /cleanup/);
      assert.ok(owned);
      assert.ok(
        owned.process().exitCode !== null ||
          owned.process().signalCode !== null,
      );
    } finally {
      await owned?.kill();
      await rm(work, { recursive: true, force: true });
    }
  },
);

test(
  "an enclosing test-runner timeout drains a profile before killing survivors",
  { timeout: 30_000 },
  async () => {
    const { readFile } = await import("node:fs/promises");
    const { z } = await import("zod");
    const { command } = await import("../../src/system/process.ts");
    const { home } = await import("../../src/config.ts");
    const work = await mkdtemp(join(tmpdir(), "sdk-profile-timeout-"));
    let processes: { browser: number; backend: number } | undefined;
    try {
      await assert.rejects(
        command(
          process.execPath,
          [
            "--import",
            join(home, "node_modules/tsx/dist/loader.mjs"),
            "--test",
            join(home, "tests/native/fixtures/timeout-profile.ts"),
          ],
          {
            timeout: 5000,
            cleanupTimeout: 5000,
            env: { SDK_TIMEOUT_WORK: work, NODE_TEST_CONTEXT: undefined },
          },
        ),
        (error: unknown) => {
          if (error instanceof AggregateError)
            throw new Error(
              error.errors
                .map((entry: unknown) =>
                  entry instanceof Error ? entry.stack : String(entry),
                )
                .join("\n"),
            );
          assert.match(String(error), /timed out/);
          return true;
        },
      );
      processes = z
        .object({ browser: z.number().int(), backend: z.number().int() })
        .parse(JSON.parse(await readFile(join(work, "ready.json"), "utf8")));
      for (const pid of Object.values(processes)) {
        assert.throws(
          () => process.kill(pid, 0),
          (error: unknown) =>
            typeof error === "object" &&
            error !== null &&
            "code" in error &&
            error.code === "ESRCH",
          `Owned profile process ${pid} survived its deadline or could not be inspected`,
        );
      }
    } finally {
      if (!processes) {
        try {
          processes = z
            .object({ browser: z.number().int(), backend: z.number().int() })
            .parse(
              JSON.parse(await readFile(join(work, "ready.json"), "utf8")),
            );
        } catch {}
      }
      for (const pid of Object.values(processes ?? {})) {
        try {
          process.kill(pid, "SIGKILL");
        } catch {}
      }
      await rm(work, { recursive: true, force: true });
    }
  },
);

test(
  "denied termination still permits bounded nonzero CLI exit",
  { timeout: 10_000 },
  async () => {
    const { readFile } = await import("node:fs/promises");
    const { command } = await import("../../src/system/process.ts");
    const { home } = await import("../../src/config.ts");
    const work = await mkdtemp(join(tmpdir(), "sdk-denied-exit-"));
    const marker = join(work, "pid");
    try {
      await assert.rejects(
        command(
          process.execPath,
          [
            "--import",
            join(home, "node_modules/tsx/dist/loader.mjs"),
            join(home, "tests/native/fixtures/denied-cleanup.ts"),
            marker,
          ],
          {
            timeout: 2000,
            cleanupTimeout: 100,
            env: { NODE_TEST_CONTEXT: undefined },
          },
        ),
        /exited 1/,
      );
    } finally {
      try {
        const pid = Number(await readFile(marker, "utf8"));
        process.kill(-pid, "SIGKILL");
      } catch {}
      await rm(work, { recursive: true, force: true });
    }
  },
);
