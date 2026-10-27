import { spawn, spawnSync, type ChildProcess } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { StringDecoder } from "node:string_decoder";
import { budgets } from "./budgets.ts";

export interface CommandOptions {
  cwd?: string;
  env?: NodeJS.ProcessEnv;
  log?: string;
  timeout?: number;
  signal?: AbortSignal;
  input?: string;
  cleanupTimeout?: number;
  maxOutputBytes?: number;
}
export interface CommandResult {
  stdout: string;
  output: string;
}

export async function command(
  program: string,
  args: readonly string[],
  options: CommandOptions = {},
): Promise<CommandResult> {
  options.signal?.throwIfAborted();
  const child = spawn(program, [...args], {
    cwd: options.cwd,
    env: { ...process.env, ...options.env },
    detached: true,
    stdio: ["pipe", "pipe", "pipe"],
  });
  let stdout = "",
    output = "",
    timedOut = false,
    overflow = false;
  const stopErrors: unknown[] = [];
  let forceSent = false;
  const outputLimit = options.maxOutputBytes ?? 16 * 1024 * 1024;
  const stdoutDecoder = new StringDecoder("utf8");
  const stderrDecoder = new StringDecoder("utf8");
  let force: ReturnType<typeof setTimeout> | undefined;
  let terminationDeadline: number | undefined;
  let rejectStop: (error: Error) => void = () => {};
  const stopExpired = new Promise<never>((_resolve, reject) => {
    rejectStop = reject;
  });
  const exited = new Promise<number | null>((resolve, reject) => {
    child.once("error", reject);
    child.once("close", resolve);
  });
  const attemptKill = (signal: NodeJS.Signals) => {
    try {
      kill(child, signal);
      if (signal === "SIGKILL") forceSent = true;
    } catch (error) {
      stopErrors.push(error);
    }
  };
  const abort = () => {
    terminationDeadline ??=
      Date.now() + (options.cleanupTimeout ?? budgets.resourceCleanup);
    attemptKill("SIGTERM");
    force ??= setTimeout(
      () => {
        attemptKill("SIGKILL");
        rejectStop(new Error(`${program} exceeded its termination grace`));
      },
      Math.max(1, terminationDeadline - Date.now()),
    );
  };
  const append = (text: string, protocol: boolean) => {
    if (overflow) return;
    output += text;
    if (protocol) stdout += text;
    if (Buffer.byteLength(output) > outputLimit) {
      overflow = true;
      output = output.slice(-outputLimit) + "\n[output budget exceeded]\n";
      stdout = "";
      abort();
    }
  };
  child.stdout.on("data", (value: Buffer) =>
    append(stdoutDecoder.write(value), true),
  );
  child.stderr.on("data", (value: Buffer) =>
    append(stderrDecoder.write(value), false),
  );
  child.stdout.on("end", () => append(stdoutDecoder.end(), true));
  child.stderr.on("end", () => append(stderrDecoder.end(), false));
  child.stdin.on("error", () => {});
  child.stdin.end(options.input);
  options.signal?.addEventListener("abort", abort, { once: true });
  const timeout = setTimeout(() => {
    timedOut = true;
    abort();
  }, options.timeout ?? 900_000);
  return withResources(
    async () => {
      let code: number | null;
      try {
        code = await Promise.race([exited, stopExpired]);
      } catch (error) {
        if (overflow)
          throw new Error(
            `${program} exceeded its ${outputLimit}-byte output budget`,
            { cause: error },
          );
        if (timedOut) throw new Error(`${program} timed out`, { cause: error });
        options.signal?.throwIfAborted();
        throw error;
      }
      if (overflow)
        throw new Error(
          `${program} exceeded its ${outputLimit}-byte output budget`,
        );
      if (timedOut) throw new Error(`${program} timed out`);
      options.signal?.throwIfAborted();
      if (code !== 0)
        throw new Error(`${program} exited ${code}\n${output.slice(-5000)}`);
      return { stdout, output };
    },
    async () => {
      // A test leader may exit before its resource-owning child. Retain the
      // original grace, then finish the group without throwing from callbacks.
      try {
        while (
          terminationDeadline &&
          Date.now() < terminationDeadline &&
          groupExists(child)
        )
          await delay(
            Math.max(1, Math.min(25, terminationDeadline - Date.now())),
          );
      } catch (error) {
        stopErrors.push(error);
      }
      if (!forceSent) attemptKill("SIGKILL");
      clearTimeout(timeout);
      clearTimeout(force);
      options.signal?.removeEventListener("abort", abort);
      releaseHandles(child);
      if (options.log) {
        try {
          await mkdir(dirname(options.log), { recursive: true });
          await writeFile(options.log, output);
        } catch (error) {
          stopErrors.push(error);
        }
      }
      if (stopErrors.length === 1) throw stopErrors[0];
      if (stopErrors.length > 1)
        throw new AggregateError(stopErrors, "Subprocess cleanup failed");
    },
  );
}

/** Establish liveness independently when the OS denies a group signal. */
function hasLiveGroupMembers(pid: number): boolean {
  const result = spawnSync("ps", ["-ax", "-o", "pgid=,state=,pid=,uid="], {
    encoding: "utf8",
    timeout: 1000,
    maxBuffer: 4 * 1024 * 1024,
  });
  if (result.error || result.status !== 0)
    throw new Error("Could not establish process-group cleanup state", {
      cause: result.error,
    });
  const relevant = result.stdout
    .split("\n")
    .filter((line) => Number(line.trim().split(/\s+/)[0]) === pid);
  return relevant.some((line) => {
    const fields = line.trim().split(/\s+/);
    return (
      Number(fields[0]) === pid &&
      fields[1] !== undefined &&
      !fields[1].startsWith("Z")
    );
  });
}

function groupExists(child: ChildProcess): boolean {
  if (!child.pid) return false;
  try {
    process.kill(-child.pid, 0);
    return true;
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "ESRCH") return false;
    if (code === "EPERM") return hasLiveGroupMembers(child.pid);
    throw error;
  }
}

/** Stop the entire process group, including grandchildren started by uv/cargo. */
export function kill(
  child: ChildProcess,
  signal: NodeJS.Signals = "SIGTERM",
): void {
  if (!child.pid) return;
  try {
    process.kill(-child.pid, signal);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code === "EPERM" && hasLiveGroupMembers(child.pid)) throw error;
    if (code !== "ESRCH" && code !== "EPERM") throw error;
    if (child.exitCode === null && child.signalCode === null)
      child.kill(signal);
  }
}

function releaseHandles(child: ChildProcess): void {
  child.stdin?.destroy();
  child.stdout?.destroy();
  child.stderr?.destroy();
  child.unref();
}

export async function stopProcess(child: ChildProcess): Promise<void> {
  let force: ReturnType<typeof setTimeout> | undefined;
  let deadline: ReturnType<typeof setTimeout> | undefined;
  let onClose: () => void = () => {};
  await withResources(
    async () => {
      if (child.exitCode !== null && child.exitCode !== 0)
        throw new Error(`Backend exited ${child.exitCode} before cleanup`);
      if (child.signalCode !== null)
        throw new Error(
          `Backend exited from ${child.signalCode} before cleanup`,
        );
      if (child.exitCode !== null) return;
      await new Promise<void>((resolve, reject) => {
        const attempt = (signal: NodeJS.Signals) => {
          try {
            kill(child, signal);
          } catch (error) {
            reject(error);
          }
        };
        force = setTimeout(() => attempt("SIGKILL"), 1500);
        deadline = setTimeout(
          () => reject(new Error("Subprocess cleanup timed out")),
          budgets.resourceCleanup,
        );
        onClose = () => {
          try {
            kill(child, "SIGKILL");
            resolve();
          } catch (error) {
            reject(error);
          }
        };
        child.once("close", onClose);
        attempt("SIGTERM");
      });
    },
    async () => {
      clearTimeout(force);
      clearTimeout(deadline);
      child.removeListener("close", onClose);
      try {
        kill(child, "SIGKILL");
      } finally {
        releaseHandles(child);
      }
    },
  );
}
export async function withResources<T>(
  run: () => Promise<T>,
  cleanup: () => Promise<void>,
): Promise<T> {
  let value: T;
  try {
    value = await run();
  } catch (error) {
    try {
      await cleanup();
    } catch (cleanupError) {
      throw new AggregateError(
        [error, cleanupError],
        "Execution and cleanup failed",
      );
    }
    throw error;
  }
  await cleanup();
  return value;
}
