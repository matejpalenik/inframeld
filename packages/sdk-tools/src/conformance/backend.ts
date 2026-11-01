import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { z } from "zod";
import { root, cache } from "../config.ts";
import {
  startProcess,
  stopProcess,
  withResources,
  type ProcessOutcome,
} from "../system/process.ts";
import { budgets, profileBudget } from "../system/budgets.ts";
import { shutdown } from "../system/shutdown.ts";
import type { JsonValue } from "./protocol.ts";

export async function controlJson(
  url: string,
  init: RequestInit = {},
  timeout: number = budgets.control,
): Promise<JsonValue> {
  const response = await fetch(url, {
    ...init,
    signal: AbortSignal.any([
      shutdown.signal,
      ...(init.signal ? [init.signal] : []),
      AbortSignal.timeout(Math.max(1, Math.floor(timeout))),
    ]),
  });
  if (!response.ok)
    throw new Error(`Fixture control ${url} returned ${response.status}`);
  return z.json().parse(await response.json());
}
export interface Backend {
  url: string;
  pid: number;
  cleanup: Promise<ProcessOutcome>;
  close(): Promise<void>;
}

export async function startBackend(
  work: string,
  origin?: string,
  signal = shutdown.signal,
  startupTimeout: number = budgets.startup,
  startupDeadline = performance.now() + startupTimeout,
  executionDeadline = performance.now() + profileBudget() + budgets.cleanup,
): Promise<Backend> {
  signal.throwIfAborted();
  const deadline = Math.min(
    startupDeadline,
    performance.now() + startupTimeout,
  );
  const lifetime = new AbortController();
  const interrupt = () => lifetime.abort(signal.reason);
  const shutdownInterrupt = () => lifetime.abort(shutdown.signal.reason);
  signal.addEventListener("abort", interrupt, { once: true });
  if (signal.aborted) interrupt();
  let child;
  try {
    child = await startProcess(
      join(root, "apps/backend/.venv/bin/python"),
      [
        "-m",
        "tests.support.sdk_server",
        "serve",
        join(work, "address"),
        ...(origin ? ["--browser-origin", origin] : []),
      ],
      {
        cwd: join(root, "apps/backend"),
        env: { UV_CACHE_DIR: join(cache, "uv") },
        mode: "backend",
        maxOutputBytes: 4 * 1024 * 1024,
        startupDeadline: deadline,
        executionDeadline,
        signal: lifetime.signal,
      },
    );
  } catch (error) {
    signal.removeEventListener("abort", interrupt);
    throw error;
  }
  let failure: Error | undefined;
  let ended = false;
  const observeOutput = () => {
    if (child.capture.overflow)
      failure ??= new Error("Backend exceeded its 4 MiB output budget");
  };
  observeOutput();
  void child.result.then(
    () => {
      ended = true;
    },
    (error: unknown) => {
      ended = true;
      observeOutput();
      failure ??=
        error instanceof Error ? error : new Error("Backend owner failed");
    },
  );
  let closing: Promise<void> | undefined;
  const close = () => {
    if (!closing) {
      signal.removeEventListener("abort", interrupt);
      shutdown.signal.removeEventListener("abort", shutdownInterrupt);
      closing = withResources(
        async () => {
          const errors: unknown[] = [];
          try {
            await stopProcess(child);
          } catch (error) {
            errors.push(error);
          }
          // Stopping can produce final output, even with successful owner evidence.
          observeOutput();
          if (failure && !errors.includes(failure)) errors.unshift(failure);
          if (errors.length === 1) throw errors[0];
          if (errors.length)
            throw new AggregateError(
              errors,
              "Backend output and cleanup failed",
            );
        },
        () => writeFile(join(work, "backend.log"), child.capture.output),
      );
    }
    return closing;
  };
  try {
    while (performance.now() < deadline) {
      signal.throwIfAborted();
      observeOutput();
      if (failure) throw failure;
      if (ended)
        throw new Error(
          `Backend exited before readiness: ${child.capture.output}`,
        );
      try {
        const url = (
          await readFile(join(work, "address"), { encoding: "utf8", signal })
        ).trim();
        await controlJson(
          url + "/health",
          { signal },
          Math.min(500, deadline - performance.now()),
        );
        signal.throwIfAborted();
        signal.removeEventListener("abort", interrupt);
        shutdown.signal.addEventListener("abort", shutdownInterrupt, {
          once: true,
        });
        shutdown.signal.throwIfAborted();
        return { url, pid: child.pid, cleanup: child.result, close };
      } catch {
        signal.throwIfAborted();
      }
      await delay(
        Math.min(50, Math.max(0, deadline - performance.now())),
        undefined,
        { signal },
      );
    }
    throw new Error(`Backend startup timed out: ${child.capture.output}`);
  } catch (error) {
    const primary = signal.aborted ? signal.reason : error;
    try {
      await close();
    } catch (cleanup) {
      throw new AggregateError(
        [primary, cleanup],
        "Backend startup and cleanup failed",
      );
    }
    throw primary;
  }
}
