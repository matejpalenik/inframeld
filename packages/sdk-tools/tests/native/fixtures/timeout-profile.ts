/** Production profile cleanup precedes the independent owner's emergency recovery. */
import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { join } from "node:path";
import { test } from "node:test";
import { startProfile } from "../../../src/conformance/profile.ts";
import {
  installInterruptHandlers,
  shutdown,
} from "../../../src/system/shutdown.ts";
import {
  openBrowserCase,
  observeProfileListener,
  expectedStalledCloseFailure,
  stalledCloseMessages,
  FixtureDiagnostics,
  fixtureDiagnostic,
} from "./browser-owner.ts";

const { chromium } = await import("playwright");
installInterruptHandlers();

if (process.env.SDK_BROWSER_OWNER_PROBE === "1") {
  const entered = performance.now();
  const client = await openBrowserCase(
    "worker-loss",
    entered + 5000,
    entered + 10000,
  );
  await client.launch({
    channel: "chromium",
    headless: true,
    timeout: Math.max(1, entered + 5000 - performance.now()),
  });
  await new Promise<void>(() => {});
} else
  test("deliberately stalled profile", async (context) => {
    const work = process.env.SDK_TIMEOUT_WORK;
    assert.ok(work);
    const entered = performance.now();
    const diagnosticFolder = process.env.SDK_TIMEOUT_DIAGNOSTICS;
    assert.ok(diagnosticFolder);
    const diagnostics = new FixtureDiagnostics("worker");
    const diagnosticFailure = () => {
      process.exitCode = 1;
      process.stderr.write(
        fixtureDiagnostic({
          phase: "fixture-terminal",
          category: "diagnostic-failed",
          status: null,
        }),
      );
    };
    const record = (phase: string, category: string) => {
      try {
        diagnostics.note({ phase, category, status: null });
        void diagnostics
          .write(diagnosticFolder, entered + 10000)
          .catch(diagnosticFailure);
      } catch {
        diagnosticFailure();
      }
    };
    record("startup", "started");
    const client = await openBrowserCase(
      "profile-timeout",
      entered + 5000,
      entered + 10000,
      "profile",
    );
    const listenerClosed = observeProfileListener(context);
    context.mock.method(
      chromium,
      "launchServer",
      (options: { channel: "chromium"; headless: true; timeout: number }) =>
        client.launch(options),
    );
    await writeFile(join(work, "driver.mjs"), "export const bindings=[];");
    const fixture = await startProfile(
      "typescript-chromium",
      { bindings: [], typescriptBundle: join(work, "driver.mjs") },
      work,
    );
    let finalizing: Promise<void> | undefined;
    const finalize = () =>
      (finalizing ??= (async () => {
        let cleanupError: string | undefined;
        let expectedGracefulFailure = false;
        let cleanupDetails: string[] = [];
        try {
          const closing = fixture.close();
          record("finalize-started", "started");
          await closing;
          record("fixture-close-settled", "passed");
        } catch (error) {
          expectedGracefulFailure = expectedStalledCloseFailure(error);
          cleanupError = expectedGracefulFailure
            ? "expected-close-deadline"
            : "profile-cleanup-failed";
          cleanupDetails = expectedGracefulFailure
            ? [
                stalledCloseMessages.find(
                  (message) =>
                    String((error as AggregateError).errors[0]) === message,
                )!,
              ]
            : ["profile-cleanup-failed"];
          record(
            "fixture-close-settled",
            expectedGracefulFailure ? "expected-close-deadline" : "failed",
          );
        }
        const backend = await fixture.backend.cleanup;
        record("backend-outcome-settled", "passed");
        const owner = await client.completion;
        record("browser-receipt-settled", "passed");
        const listener = listenerClosed();
        await writeFile(
          join(work, "cleanup.json"),
          JSON.stringify({
            backend,
            owner,
            browser:
              owner.origin === "profile" &&
              owner.fulfilled &&
              owner.closeObserved,
            listener,
            profileComplete: listener,
            cleanupError,
            expectedGracefulFailure,
            cleanupDetails,
          }),
        );
        record("cleanup-report-written", "passed");
        client.end();
      })());
    let observeShutdown!: () => void;
    const shutdownObserved = new Promise<void>((resolve) => {
      observeShutdown = resolve;
    });
    const onShutdown = () => {
      record("shutdown-observed", "started");
      const finishing = finalize();
      void finishing.catch(() => {
        process.stderr.write(
          fixtureDiagnostic({
            phase: "fixture-terminal",
            category: "cleanup-failed",
            status: null,
          }),
        );
      });
      observeShutdown();
    };
    shutdown.signal.addEventListener("abort", onShutdown, { once: true });
    if (shutdown.signal.aborted) onShutdown();
    await writeFile(
      join(work, "ready.json"),
      JSON.stringify({
        backend: fixture.backend.pid,
      }),
    );
    record("ready", "passed");
    // The separately surviving launcher owns emergency BrowserServer recovery.
    // This process contributes only normal cached profile finalization.
    await shutdownObserved;
    await finalize();
  });
