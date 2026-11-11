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
import type { CommandObservation } from "../../src/system/process.ts";
import { setTimeout as delay } from "node:timers/promises";
import {
  readDeniedUncertainReceipt,
  withDeniedFixtureRecovery,
} from "./fixtures/denied-cleanup.ts";
import childProcess, { execFile, type SpawnOptions } from "node:child_process";
import { syncBuiltinESMExports } from "node:module";
import { fileURLToPath } from "node:url";
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
  async (context) => {
    const testDeadline = performance.now() + 60000;
    const { z } = await import("zod");
    const { command, hasConfirmedCleanup, withResources } =
      await import("../../src/system/process.ts");
    const { home } = await import("../../src/config.ts");
    const work = await mkdtemp(join(tmpdir(), "sdk-denied-exit-"));
    const marker = join(work, "pid");
    const owner = fileURLToPath(
      new URL("../../src/system/process_owner.py", import.meta.url),
    );
    const spawn = childProcess.spawn;
    const ownerClosures: Promise<number | null>[] = [];
    let observation: Readonly<CommandObservation> | undefined;
    const observedSpawn = context.mock.method(childProcess, "spawn", ((
      program: string,
      args: readonly string[],
      options: SpawnOptions,
    ) => {
      const child = spawn(program, [...args], options);
      if (program === "python3" && args.at(-1) === owner)
        ownerClosures.push(
          new Promise((resolve) => child.once("close", resolve)),
        );
      return child;
    }) as typeof spawn);
    syncBuiltinESMExports();
    const verifyDeniedExit = async () => {
      let check = "SDK_DENIED_COMMAND_EXIT";
      let commandFailure: unknown;
      let settlement: "fulfilled" | "rejected" | "unknown" = "unknown";
      let reportedCleanupConfirmed = false;
      try {
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
              observeOutcome(value) {
                observation = value;
              },
            },
          ).then(
            (value) => {
              settlement = "fulfilled";
              reportedCleanupConfirmed =
                observation?.closeResult === "resolved";
              return value;
            },
            (error: unknown) => {
              commandFailure = error;
              settlement = "rejected";
              reportedCleanupConfirmed = hasConfirmedCleanup(error);
              throw error;
            },
          ),
          (error: unknown) => {
            // Nonzero exit and cleanup certainty are separate owner observations.
            assert.ok(error instanceof Error);
            assert.equal(settlement, "rejected");
            assert.equal(observation?.status, 1);
            assert.equal(observation?.reason, "target-exit");
            assert.equal(observation?.stopReason, "target-exit");
            assert.equal(observation?.leaderReaped, true);
            if (observation?.closeResult === "resolved") {
              assert.equal(observation.groupState, "quiescent");
              assert.equal(reportedCleanupConfirmed, true);
            } else {
              assert.equal(observation?.closeResult, "rejected");
              assert.ok(
                ["unknown", "quiescent"].includes(
                  observation?.groupState ?? "",
                ),
              );
              assert.equal(reportedCleanupConfirmed, false);
            }
            return true;
          },
        );
        check = "SDK_DENIED_UNCERTAIN_READ";
        const uncertainText = await readDeniedUncertainReceipt(
          work,
          Math.min(testDeadline, began + 45000),
        );
        check = "SDK_DENIED_UNCERTAIN_JSON";
        const uncertainValue: unknown = JSON.parse(uncertainText);
        check = "SDK_DENIED_UNCERTAIN_SCHEMA";
        const uncertain = z
          .object({
            unknown: z.literal(true),
            ownerResult: z.literal(1),
            helper: z.number().int().positive(),
            targets: z.array(z.number().int().positive()).min(1),
          })
          .parse(uncertainValue);
        check = "SDK_DENIED_MARKER_READ";
        const pid = Number(await readFile(marker, "utf8"));
        check = "SDK_DENIED_FAILURE_READ";
        const failureText = await readFile(join(work, "failure.json"), "utf8");
        check = "SDK_DENIED_FAILURE_JSON";
        const failureValue: unknown = JSON.parse(failureText);
        check = "SDK_DENIED_FAILURE_SCHEMA";
        const failures = z
          .object({ primary: z.string(), cleanup: z.string() })
          .parse(failureValue);
        check = "SDK_DENIED_ORIGINAL_ERRORS";
        assert.match(failures.primary, /expected fixture cancellation/);
        assert.match(failures.cleanup, /cleanup/i);
        check = "SDK_DENIED_TARGET_MATCH";
        assert.ok(uncertain.targets.includes(pid));
        check = "SDK_DENIED_CLOCK_BUDGET";
        assert.ok(
          performance.now() - began < 45000,
          "Incomplete outcome must fit the original execution allowance",
        );
        check = "SDK_DENIED_PS_OBSERVATION";
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
        check = "SDK_DENIED_TARGET_LIVE";
        assert.ok(
          state.stdout.split("\n").some((row) => {
            const [candidate, status] = row.trim().split(/\s+/);
            return (
              Number(candidate) === pid && status && !status.startsWith("Z")
            );
          }),
          "The independent safety fuse must not satisfy the cleanup assertion",
        );
      } catch (error) {
        const cause =
          check === "SDK_DENIED_COMMAND_EXIT"
            ? {
                command: {
                  status: null,
                  reason: "unknown",
                  stopReason: "unknown",
                  groupState: "unknown",
                  closeResult: "unknown",
                  ...observation,
                  settlement,
                  reportedCleanupConfirmed,
                },
                cause:
                  commandFailure === undefined
                    ? error
                    : new AggregateError(
                        [commandFailure, error],
                        "Command rejection and failed assertion",
                      ),
              }
            : error;
        throw Object.assign(new Error(check, { cause }), {
          code: check,
        });
      }
    };
    await withResources(
      () => withDeniedFixtureRecovery(work, testDeadline, verifyDeniedExit),
      async () => {
        try {
          // Reconcile fixture custody without changing the earlier incomplete outcome.
          const closed = await withinDeadline(
            Promise.all(ownerClosures),
            Math.max(0, testDeadline - performance.now()),
          );
          assert.equal(closed.length, 1);
          if (observation?.closeResult === "resolved")
            assert.equal(closed[0], 0);
          else assert.ok(closed[0] === 0 || closed[0] === 1);
        } catch (cause) {
          throw Object.assign(
            new Error("SDK_DENIED_OUTER_CUSTODY", { cause }),
            {
              code: "SDK_DENIED_OUTER_CUSTODY",
            },
          );
        } finally {
          observedSpawn.mock.restore();
          syncBuiltinESMExports();
        }
      },
    );
  },
);
