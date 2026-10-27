import { spawn } from "node:child_process";
import { readFile, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { z } from "zod";
import { root, cache } from "../config.ts";
import { kill, stopProcess, withResources } from "../system/process.ts";
import { budgets } from "../system/budgets.ts";
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
      AbortSignal.timeout(Math.max(1, timeout)),
    ]),
  });
  if (!response.ok)
    throw new Error(`Fixture control ${url} returned ${response.status}`);
  return z.json().parse(await response.json());
}
export interface Backend {
  url: string;
  pid: number;
  close(): Promise<void>;
}

export async function startBackend(
  work: string,
  origin?: string,
  signal = shutdown.signal,
  startupTimeout: number = budgets.startup,
): Promise<Backend> {
  signal.throwIfAborted();
  const address = join(work, "address");
  const child = spawn(
    join(root, "apps/backend/.venv/bin/python"),
    [
      "-m",
      "tests.support.sdk_server",
      "serve",
      address,
      ...(origin ? ["--browser-origin", origin] : []),
    ],
    {
      cwd: join(root, "apps/backend"),
      // The profile owns this process group so forced profile cleanup reaches the fixture Python process.
      detached: false,
      env: { ...process.env, UV_CACHE_DIR: join(cache, "uv") },
      stdio: ["ignore", "pipe", "pipe"],
    },
  );
  let output = "";
  let failure: Error | undefined;
  const append = (value: Buffer) => {
    if (failure) return;
    output += value.toString();
    if (Buffer.byteLength(output) > 4 * 1024 * 1024) {
      output = output.slice(-4 * 1024 * 1024);
      failure = new Error("Backend exceeded its 4 MiB output budget");
      kill(child);
    }
  };
  child.stdout.on("data", append);
  child.stderr.on("data", append);
  child.on("error", (error) => {
    failure = error;
  });
  const interrupt = () => kill(child);
  signal.addEventListener("abort", interrupt, { once: true });
  const close = async () => {
    signal.removeEventListener("abort", interrupt);
    shutdown.signal.removeEventListener("abort", interrupt);
    await withResources(
      async () => {
        if (failure) throw failure;
      },
      () =>
        withResources(
          async () => {
            if (!(shutdown.signal.aborted && child.signalCode))
              await stopProcess(child);
          },
          () => writeFile(join(work, "backend.log"), output),
        ),
    );
  };
  try {
    const deadline = Date.now() + startupTimeout;
    while (Date.now() < deadline) {
      signal.throwIfAborted();
      if (failure) throw failure;
      if (child.exitCode !== null) throw new Error(`Backend exited: ${output}`);
      try {
        const url = (
          await readFile(address, { encoding: "utf8", signal })
        ).trim();
        await controlJson(
          url + "/health",
          { signal },
          Math.min(500, deadline - Date.now()),
        );
        signal.throwIfAborted();
        signal.removeEventListener("abort", interrupt);
        shutdown.signal.addEventListener("abort", interrupt, { once: true });
        shutdown.signal.throwIfAborted();
        if (!child.pid) throw new Error("Backend has no process identity");
        return { url, pid: child.pid, close };
      } catch {
        signal.throwIfAborted();
      }
      await delay(50, undefined, { signal });
    }
    throw new Error(`Backend startup timed out: ${output}`);
  } catch (error) {
    try {
      await close();
    } catch (cleanup) {
      throw new AggregateError(
        [error, cleanup],
        "Backend startup and cleanup failed",
      );
    }
    throw error;
  }
}
