/** Actual browser and profile ownership, independent of pure protocol cases. */
import assert from "node:assert/strict";
import {
  chmod,
  mkdtemp,
  rm,
  writeFile,
  readFile,
  lstat,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import { withDeniedFixtureRecovery } from "./fixtures/denied-cleanup.ts";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { cache } from "../../src/config.ts";
import { startProfile } from "../../src/conformance/profile.ts";
import { withinDeadline } from "../../src/system/deadline.ts";
import {
  openBrowserCase,
  observeProfileListener,
  expectedStalledCloseFailure,
  stalledCloseMessages,
  publishFixtureDiagnostics,
} from "./fixtures/browser-owner.ts";
import {
  FixtureDiagnostics,
  fixtureDiagnostic,
  prepareFixtureCapture,
  observeFixtureController,
  type FixtureCapture,
} from "./fixtures/fixture-diagnostics.ts";

process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(cache, "browsers");
const { chromium } = await import("playwright");

test(
  "startup cancellation closes a browser acquired before the fixture returns",
  { timeout: 90_000 },
  async (context) => {
    const entered = performance.now();
    const work = await mkdtemp(join(tmpdir(), "sdk-startup-cancel-"));
    const controller = new AbortController();
    const signal = controller.signal;
    const client = await openBrowserCase(
      "startup-cancel",
      entered + 30000,
      entered + 60000,
    );
    let confirmed = false;
    context.mock.method(
      chromium,
      "launchServer",
      async (options: {
        channel: "chromium";
        headless: true;
        timeout: number;
      }) => {
        const browser = await client.launch(options);
        controller.abort(new Error("cancel startup after browser allocation"));
        return browser;
      },
    );
    try {
      await writeFile(join(work, "driver.mjs"), "export const bindings=[];");
      await assert.rejects(
        startProfile(
          "typescript-chromium",
          { bindings: [], typescriptBundle: join(work, "driver.mjs") },
          work,
          signal,
        ),
        /cancel startup/,
      );
      assert.equal((await client.completion).origin, "profile");
      confirmed = true;
    } finally {
      client.end();
      if (confirmed) await rm(work, { recursive: true, force: true });
      else
        process.stderr.write(
          fixtureDiagnostic({
            phase: "fixture-terminal",
            category: "owner-unknown",
            caseId: "startup-cancel",
            status: null,
          }),
        );
    }
  },
);

test(
  "a stalled browser close is force-killed and remains a cleanup failure",
  { timeout: 90_000 },
  async (context) => {
    const entered = performance.now();
    const work = await mkdtemp(join(tmpdir(), "sdk-browser-kill-"));
    const client = await openBrowserCase(
      "stalled-close",
      entered + 30000,
      entered + 60000,
    );
    const listenerClosed = observeProfileListener(context);
    let confirmed = false;
    context.mock.method(
      chromium,
      "launchServer",
      (options: { channel: "chromium"; headless: true; timeout: number }) =>
        client.launch(options),
    );
    try {
      await writeFile(join(work, "driver.mjs"), "export const bindings=[];");
      const fixture = await startProfile(
        "typescript-chromium",
        { bindings: [], typescriptBundle: join(work, "driver.mjs") },
        work,
      );
      await assert.rejects(fixture.close(), (error: unknown) => {
        assert.ok(
          expectedStalledCloseFailure(error),
          "Unexpected profile cleanup failure",
        );
        return true;
      });
      const receipt = await client.completion;
      assert.equal(receipt.origin, "profile");
      assert.equal(receipt.operation, "kill");
      assert.equal(listenerClosed(), true);
      confirmed = true;
    } finally {
      client.end();
      if (confirmed) await rm(work, { recursive: true, force: true });
      else
        process.stderr.write(
          fixtureDiagnostic({
            phase: "fixture-terminal",
            category: "owner-unknown",
            caseId: "stalled-close",
            status: null,
          }),
        );
    }
  },
);

test(
  "an enclosing test-runner timeout drains a profile before killing survivors",
  { timeout: 90_000 },
  async () => {
    const { z } = await import("zod");
    const { command } = await import("../../src/system/process.ts");
    const { home } = await import("../../src/config.ts");
    const entered = performance.now();
    const work = await mkdtemp(join(tmpdir(), "sdk-profile-timeout-"));
    const supervisor = await openBrowserCase(
      "profile-timeout",
      entered + 35000,
      entered + 50000,
    );
    let confirmed = false;
    const controller = new AbortController();
    let running: Promise<unknown> | undefined;
    let stopDeadline = entered + 50000;
    const diagnostics = new FixtureDiagnostics("assertion"),
      errors: unknown[] = [];
    let protectedFolder: string | undefined,
      capture: FixtureCapture | undefined;
    let phase = "timeout-assertion";
    try {
      protectedFolder = await mkdtemp(work + ".protected-");
      await chmod(protectedFolder, 0o700);
      capture = await withinDeadline(
        prepareFixtureCapture(protectedFolder, "timeout"),
        Math.max(0, entered + 35000 - performance.now()),
      );
      diagnostics.note({ phase, category: "started", status: null });
      running = observeFixtureController(diagnostics, "nested-controller", () =>
        command(
          process.execPath,
          [
            "--import",
            join(home, "node_modules/tsx/dist/loader.mjs"),
            join(home, "tests/native/fixtures/timeout-profile.ts"),
          ],
          {
            timeout: 60000,
            cleanupTimeout: 15000,
            executionDeadline: entered + 60000,
            signal: controller.signal,
            log: capture!.path,
            env: {
              SDK_TIMEOUT_WORK: work,
              SDK_TIMEOUT_DIAGNOSTICS: protectedFolder,
              SDK_BROWSER_OWNER_CASE_CAP: supervisor.nonce,
              NODE_TEST_CONTEXT: undefined,
            },
          },
        ),
      );
      void running.catch(() => {});
      const ready = async () => {
        while (performance.now() < entered + 30000) {
          try {
            z.object({ backend: z.number().int().positive() }).parse(
              JSON.parse(await readFile(join(work, "ready.json"), "utf8")),
            );
            return;
          } catch (error) {
            if (
              !(error instanceof SyntaxError) &&
              (error as NodeJS.ErrnoException).code !== "ENOENT"
            )
              throw error;
          }
          await delay(25, undefined, { signal: controller.signal });
        }
        throw new Error(
          "Profile fixture did not become ready within 30 seconds",
        );
      };
      await Promise.race([
        ready(),
        running.then(() => {
          throw new Error("Profile fixture exited before readiness");
        }),
      ]);
      // Startup has its own allowance. Only a ready profile enters the timeout scenario.
      await delay(5000);
      stopDeadline = performance.now() + 15000;
      controller.abort(new Error("Enclosing test runner timed out"));
      await assert.rejects(running, (error: unknown) => {
        // The longer allowance still requires complete outer owner evidence.
        assert.ok(!(error instanceof AggregateError), String(error));
        assert.match(String(error), /timed out/);
        return true;
      });
      diagnostics.note({ phase, category: "passed", status: null });
      phase = "receipt-read";
      diagnostics.note({ phase, category: "started", status: null });
      const receipt = z
        .object({
          backend: z.object({
            leaderReaped: z.literal(true),
            groupState: z.literal("quiescent"),
            errors: z.array(z.string()).length(0),
          }),
          browser: z.literal(true),
          listener: z.literal(true),
          profileComplete: z.literal(true),
          owner: z.object({
            ownerId: z.string().regex(/^[a-f0-9]{64}$/),
            requestId: z.number().int().positive(),
            origin: z.literal("profile"),
            fulfilled: z.literal(true),
            closeObserved: z.literal(true),
          }),
          cleanupError: z.string().min(1),
          expectedGracefulFailure: z.literal(true),
          cleanupDetails: z.array(z.enum(stalledCloseMessages)).length(1),
        })
        .parse(JSON.parse(await readFile(join(work, "cleanup.json"), "utf8")));
      const workerStatus = join(protectedFolder, "worker-status.json");
      const workerFile = await lstat(workerStatus);
      assert.ok(
        workerFile.isFile() &&
          (workerFile.mode & 0o777) === 0o600 &&
          workerFile.size <= 4096,
      );
      const workerRecords: unknown = JSON.parse(
        await readFile(workerStatus, "utf8"),
      );
      assert.ok(Array.isArray(workerRecords));
      const workerFacts = workerRecords.map(
        (record: unknown) =>
          JSON.parse(fixtureDiagnostic(record)) as {
            phase: string;
            category: string;
          },
      );
      assert.ok(
        workerFacts.some(
          (record) =>
            record.phase === "cleanup-report-written" &&
            record.category === "passed",
        ),
        "Worker diagnostics must complete without concealing a diagnostic failure",
      );
      phase = "receipt-match";
      diagnostics.note({ phase, category: "started", status: null });
      assert.equal(receipt.browser, true);
      const independent = await supervisor.completion;
      assert.equal(independent.ownerId, receipt.owner.ownerId);
      assert.equal(independent.requestId, receipt.owner.requestId);
      assert.ok(
        performance.now() < stopDeadline,
        "Production evidence must precede emergency recovery and the original 15-second stop deadline",
      );
      confirmed = true;
      diagnostics.note({ phase, category: "passed", status: null });
    } catch (error) {
      errors.push(error);
      try {
        diagnostics.note({
          phase,
          category: "failed",
          status: null,
          failure: error,
        });
      } catch (diagnostic) {
        errors.push(diagnostic);
      }
    } finally {
      controller.abort(new Error("Profile fixture assertion finished"));
      if (running) {
        try {
          await running;
        } catch (error) {
          if (error instanceof AggregateError && !errors.includes(error))
            errors.push(error);
        }
      }
      try {
        diagnostics.note({
          phase: "assertion-finally",
          category: confirmed ? "passed" : "failed",
          status: null,
        });
      } catch (error) {
        errors.push(error);
      }
      supervisor.end();
      try {
        if (confirmed) await rm(work, { recursive: true, force: true });
        else
          process.stderr.write(
            fixtureDiagnostic({
              phase: "fixture-terminal",
              category: "owner-unknown",
              caseId: "profile-timeout",
              status: null,
            }),
          );
      } catch (error) {
        errors.push(error);
      }
      if (protectedFolder) {
        if (capture) {
          try {
            const metadata = await withinDeadline(
              capture.check(),
              Math.max(0, entered + 50000 - performance.now()),
            );
            diagnostics.note({
              phase: "nested-controller",
              category: "capture-checked",
              slot: "timeout",
              ...metadata,
              status: null,
            });
          } catch (error) {
            errors.push(error);
            try {
              diagnostics.note({
                phase: "nested-controller",
                category: "capture-invalid",
                slot: "timeout",
                status: null,
              });
            } catch (diagnostic) {
              errors.push(diagnostic);
            }
          }
        }
        try {
          await publishFixtureDiagnostics(
            diagnostics,
            protectedFolder,
            entered + 50000,
          );
        } catch (error) {
          errors.push(error);
        }
      }
    }
    if (errors.length === 1) throw errors[0];
    if (errors.length)
      throw new AggregateError(
        errors,
        "Profile assertion and diagnostics failed",
      );
  },
);

test(
  "denied termination still permits bounded nonzero CLI exit",
  { timeout: 60_000 },
  async () => {
    const testDeadline = performance.now() + 60000;
    const { z } = await import("zod");
    const { command } = await import("../../src/system/process.ts");
    const { home } = await import("../../src/config.ts");
    const work = await mkdtemp(join(tmpdir(), "sdk-denied-exit-"));
    const marker = join(work, "pid");
    await withDeniedFixtureRecovery(work, testDeadline, async () => {
      const began = performance.now();
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
            timeout: 45000,
            cleanupTimeout: 100,
            env: { NODE_TEST_CONTEXT: undefined },
          },
        ),
        /exited 1/,
      );
      const uncertain = z
        .object({
          unknown: z.literal(true),
          ownerResult: z.literal(1),
          helper: z.number().int().positive(),
          targets: z.array(z.number().int().positive()).min(1),
        })
        .parse(
          JSON.parse(await readFile(join(work, "uncertain.json"), "utf8")),
        );
      const pid = Number(await readFile(marker, "utf8"));
      const failures = z
        .object({ primary: z.string(), cleanup: z.string() })
        .parse(JSON.parse(await readFile(join(work, "failure.json"), "utf8")));
      assert.match(failures.primary, /expected fixture cancellation/);
      assert.match(failures.cleanup, /cleanup/i);
      assert.ok(uncertain.targets.includes(pid));
      assert.ok(
        performance.now() - began < 45000,
        "Incomplete outcome must fit the original execution allowance",
      );
      const observationEnvironment: NodeJS.ProcessEnv = {
        ...process.env,
        LC_ALL: "C",
      };
      for (const key of ["PS_PERSONALITY", "CMD_ENV", "I_WANT_A_BROKEN_PS"])
        delete observationEnvironment[key];
      const state = await promisify(execFile)(
        "ps",
        ["-A", "-o", "pid=,stat="],
        {
          env: observationEnvironment,
          timeout: Math.max(
            1,
            Math.floor(Math.min(5000, began + 45000 - performance.now())),
          ),
          maxBuffer: 4 * 1024 * 1024,
        },
      );
      assert.ok(
        state.stdout.split("\n").some((row) => {
          const [candidate, status] = row.trim().split(/\s+/);
          return Number(candidate) === pid && status && !status.startsWith("Z");
        }),
        "The independent safety fuse must not satisfy the cleanup assertion",
      );
    });
  },
);
