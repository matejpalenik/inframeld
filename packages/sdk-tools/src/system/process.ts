import { spawn, type ChildProcess } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import type { Duplex, Readable } from "node:stream";
import { StringDecoder } from "node:string_decoder";
import { fileURLToPath } from "node:url";
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
  startupDeadline?: number;
  executionDeadline?: number;
  mode?: "command" | "backend";
}
export interface CommandResult {
  stdout: string;
  output: string;
}
export interface ProcessOutcome {
  status: number | null;
  reason: string;
  leaderReaped: boolean;
  groupState: "quiescent" | "live" | "unknown";
  errors: string[];
}
export interface OwnedProcess {
  readonly pid: number;
  readonly capture: Readonly<{
    stdout: string;
    output: string;
    received: number;
    overflow: boolean;
  }>;
  readonly result: Promise<ProcessOutcome>;
  readonly stopReason: string | undefined;
  requestStop(reason: "close" | "cancel" | "timeout" | "overflow"): void;
  close(): Promise<void>;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  void promise.catch(() => {});
  return { promise, resolve, reject };
}

const owned = new WeakSet<OwnedProcess>();
const stopped = new WeakMap<OwnedProcess, Promise<void>>();
const helperPath = fileURLToPath(
  new URL("./process_owner.py", import.meta.url),
);

/** Node owns pipes and deadlines. Only the Python sole waiter may signal target groups. */
class ProcessOwner implements OwnedProcess {
  pid = 0;
  private readonly stdout: Readable;
  private readonly stderr: Readable;
  readonly capture = { stdout: "", output: "", received: 0, overflow: false };
  private readonly decoders = [
    new StringDecoder("utf8"),
    new StringDecoder("utf8"),
  ];
  private readonly outputLimit: number;
  readonly result: Promise<ProcessOutcome>;
  readonly started = deferred<void>();
  stopReason: string | undefined;
  private readonly completion = deferred<ProcessOutcome>();
  private readonly helper: ChildProcess;
  private readonly control: Duplex;
  private readonly executionDeadline: number;
  private readonly startupDeadline: number;
  private readonly cleanupBudget: number;
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();
  private clock: { helper: number; node: number } | undefined;
  private buffer = Buffer.alloc(0);
  private startSubmitted = false;
  private startComplete = false;
  private terminal: ProcessOutcome | undefined;
  private refused = false;
  private helperCode: number | null | undefined;
  private helperClosed = false;
  private settled = false;
  private stopDeadline: number | undefined;
  private closing: Promise<void> | undefined;
  private failure: Error | undefined;
  private exited = false;
  private frames = 0;
  private readonly abort = () => this.requestStop("cancel");

  constructor(
    private readonly program: string,
    private readonly args: readonly string[],
    private readonly options: CommandOptions,
    entered: number,
  ) {
    this.result = this.completion.promise;
    this.outputLimit = options.maxOutputBytes ?? 16 * 1024 * 1024;
    this.executionDeadline = Math.min(
      entered + (options.timeout ?? 900_000),
      options.executionDeadline ?? Number.POSITIVE_INFINITY,
    );
    this.startupDeadline = Math.min(
      this.executionDeadline,
      options.startupDeadline ?? this.executionDeadline,
    );
    this.cleanupBudget = options.cleanupTimeout ?? budgets.resourceCleanup;
    if (
      !Number.isFinite(this.executionDeadline) ||
      !Number.isFinite(this.startupDeadline) ||
      !Number.isSafeInteger(this.cleanupBudget) ||
      this.cleanupBudget <= 0
    )
      throw new Error("Invalid subprocess deadline or cleanup budget");
    // Watchdogs begin before spawn and control startup, without adding a handshake period.
    this.at(this.executionDeadline, () => this.requestStop("timeout"));
    this.at(this.startupDeadline, () => {
      if (!this.pid) {
        this.started.reject(new Error(`${program} startup timed out`));
        this.requestStop("timeout");
      }
    });
    this.helper = spawn("python3", ["-I", "-S", "-B", helperPath], {
      stdio: ["pipe", "pipe", "pipe", "pipe"],
      detached: true,
    });
    this.stdout = this.helper.stdout!;
    this.stderr = this.helper.stderr!;
    for (const [index, stream] of [this.stdout, this.stderr].entries()) {
      stream.on("data", (chunk: Buffer) => this.append(chunk, index));
      stream.on("end", () => {
        if (this.capture.overflow) return;
        const tail = this.decoders[index]!.end();
        this.capture.output += tail;
        if (index === 0) this.capture.stdout += tail;
      });
      stream.on("error", (error) => this.fail(error));
    }
    this.control = this.helper.stdio[3] as Duplex;
    this.control.on("data", (chunk: Buffer) => {
      try {
        this.receive(chunk);
      } catch (error) {
        this.buffer = Buffer.alloc(0);
        this.control.pause();
        this.fail(
          new Error("Invalid process owner UTF-8/JSON/state control document"),
        );
      }
    });
    this.control.on("error", (error) => this.fail(error));
    this.control.once("end", () => {
      if (this.buffer.length || (!this.terminal && !this.refused))
        this.fail(
          new Error(
            "Process owner control closed before complete terminal evidence",
          ),
        );
    });
    this.helper.stdin!.on("error", (error: NodeJS.ErrnoException) => {
      if (error.code !== "EPIPE") this.fail(error);
    });
    this.helper.once("error", (error) => this.fail(error));
    this.helper.once("exit", (code) => {
      this.helperCode = code;
      if (!this.terminal && !this.refused) this.beginStop("owner-exit");
    });
    this.helper.once("close", () => {
      this.helperClosed = true;
      this.finish();
    });
    options.signal?.addEventListener("abort", this.abort, { once: true });
    owned.add(this);
    if (options.signal?.aborted) this.requestStop("cancel");
  }

  private append(chunk: Buffer, index: number): void {
    this.capture.received += chunk.length;
    if (this.capture.overflow) return;
    const text = this.decoders[index]!.write(chunk);
    this.capture.output += text;
    if (index === 0) this.capture.stdout += text;
    if (this.capture.received > this.outputLimit) {
      this.capture.overflow = true;
      this.capture.stdout = "";
      this.capture.output =
        Buffer.from(this.capture.output)
          .subarray(-this.outputLimit)
          .toString("utf8") + "\n[output budget exceeded]\n";
      this.requestStop("overflow");
    }
  }

  private at(deadline: number, action: () => void): void {
    const timer = setTimeout(action, Math.max(0, deadline - performance.now()));
    this.timers.add(timer);
  }

  private mapped(deadline: number): number {
    if (!this.clock) throw new Error("Process owner has no clock anchor");
    return Math.floor(this.clock.helper + deadline - this.clock.node);
  }

  private fail(error: unknown): void {
    this.failure ??=
      error instanceof Error
        ? error
        : new Error("Process owner control failed");
    this.started.reject(this.failure);
    this.requestStop("close");
  }

  private async send(value: object, deadline: number): Promise<void> {
    const payload = Buffer.from(
      JSON.stringify({ version: 1, ...value }) + "\n",
    );
    if (payload.length > 1024 * 1024)
      throw new Error("Process owner start document is too large");
    const end = Math.min(deadline, performance.now() + budgets.control);
    for (let offset = 0; offset < payload.length; offset += 16384) {
      const remaining = end - performance.now();
      if (remaining <= 0)
        throw new Error("Process owner control deadline expired");
      await new Promise<void>((resolve, reject) => {
        const timer = setTimeout(
          () => reject(new Error("Process owner control timed out")),
          remaining,
        );
        this.timers.add(timer);
        this.control.write(
          payload.subarray(offset, offset + 16384),
          (error) => {
            clearTimeout(timer);
            this.timers.delete(timer);
            if (error) reject(error);
            else resolve();
          },
        );
      });
    }
  }

  private receive(chunk: Buffer): void {
    this.buffer = Buffer.concat([this.buffer, chunk]);
    if (this.buffer.length > 65536)
      throw new Error("Process owner control exceeded its byte budget");
    let boundary: number;
    while ((boundary = this.buffer.indexOf(10)) >= 0) {
      const bytes = this.buffer.subarray(0, boundary);
      this.buffer = this.buffer.subarray(boundary + 1);
      if (bytes.length > 16384 || ++this.frames > 5)
        throw new Error("Process owner frame budget exceeded");
      const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
      const parsed: unknown = JSON.parse(text);
      if (
        !parsed ||
        typeof parsed !== "object" ||
        Array.isArray(parsed) ||
        JSON.stringify(parsed) !== text
      )
        throw new Error("Invalid process owner control document");
      const value = parsed as Record<string, unknown>;
      if (value.version !== 1)
        throw new Error("Unsupported process owner protocol");
      const fields = (...names: string[]) => {
        if (
          Object.keys(value).sort().join() !==
          ["version", "type", ...names].sort().join()
        )
          throw new Error("Unexpected process owner fields");
      };
      switch (value.type) {
        case "ready": {
          fields("clock", "python");
          if (
            this.clock ||
            this.startSubmitted ||
            !Number.isSafeInteger(value.clock) ||
            typeof value.python !== "string"
          )
            throw new Error("Invalid process owner ready state");
          this.clock = {
            helper: value.clock as number,
            node: performance.now(),
          };
          if (this.stopReason || performance.now() >= this.startupDeadline) {
            this.requestStop(
              this.stopReason === "cancel" ? "cancel" : "timeout",
            );
            this.control.end();
            break;
          }
          const environment = Object.fromEntries(
            Object.entries({ ...process.env, ...this.options.env }).filter(
              (entry) => entry[1] !== undefined,
            ),
          );
          this.startSubmitted = true;
          void this.send(
            {
              type: "start",
              argv: [this.program, ...this.args],
              cwd: this.options.cwd ?? null,
              env: environment,
              executionDeadline: this.mapped(this.executionDeadline),
              startupDeadline: this.mapped(this.startupDeadline),
              cleanupMs: this.cleanupBudget,
              mode: this.options.mode ?? "command",
            },
            this.startupDeadline,
          )
            .then(() => {
              this.startComplete = true;
              if (this.stopReason) this.sendStop();
            })
            .catch((error: unknown) => this.fail(error));
          break;
        }
        case "started":
          fields("pid");
          if (
            !this.startSubmitted ||
            this.pid ||
            !Number.isSafeInteger(value.pid) ||
            (value.pid as number) <= 0
          )
            throw new Error("Invalid process owner acquisition state");
          this.pid = value.pid as number;
          this.helper.stdin!.end(this.options.input);
          this.started.resolve();
          break;
        case "exited":
          fields("status");
          if (
            !this.pid ||
            this.exited ||
            this.terminal ||
            !Number.isSafeInteger(value.status)
          )
            throw new Error("Invalid process owner exit state");
          this.exited = true;
          this.beginStop("target-exit");
          break;
        case "refused":
          fields("reason");
          if (
            this.pid ||
            this.terminal ||
            this.refused ||
            typeof value.reason !== "string"
          )
            throw new Error("Invalid process owner refusal");
          this.refused = true;
          this.started.reject(
            new Error(
              `Process owner refused startup: ${value.reason}. Use the pinned Python 3.13 toolchain.`,
            ),
          );
          break;
        case "finished": {
          fields("status", "reason", "leaderReaped", "groupState", "errors");
          if (
            !this.pid ||
            this.terminal ||
            (value.status !== null && !Number.isSafeInteger(value.status)) ||
            typeof value.reason !== "string" ||
            typeof value.leaderReaped !== "boolean" ||
            !["quiescent", "live", "unknown"].includes(
              String(value.groupState),
            ) ||
            !Array.isArray(value.errors) ||
            value.errors.length > 16 ||
            !value.errors.every(
              (item: unknown) =>
                typeof item === "string" && /^[a-z-]{1,64}$/.test(item),
            )
          )
            throw new Error("Invalid process owner terminal evidence");
          this.terminal = {
            status: value.status as number | null,
            reason: value.reason,
            leaderReaped: value.leaderReaped,
            groupState: value.groupState as ProcessOutcome["groupState"],
            errors: value.errors as string[],
          };
          this.beginStop(value.reason);
          break;
        }
        default:
          throw new Error("Unknown process owner message");
      }
    }
  }

  private beginStop(reason: string): void {
    if (this.stopDeadline !== undefined) return;
    this.stopReason = reason;
    this.stopDeadline = performance.now() + this.cleanupBudget;
    this.at(this.stopDeadline, () => {
      this.failure ??= new Error(
        "Subprocess cleanup timed out. Cleanup may be incomplete.",
      );
      this.finish(true);
    });
  }

  requestStop(reason: "close" | "cancel" | "timeout" | "overflow"): void {
    if (this.settled) return;
    this.beginStop(reason);
    if (!this.startSubmitted) this.control.end();
    else if (!this.startComplete) this.control.end();
    else this.sendStop();
  }

  private sentStop = false;
  private sendStop(): void {
    if (
      this.sentStop ||
      !this.clock ||
      this.stopDeadline === undefined ||
      this.control.writableEnded
    )
      return;
    this.sentStop = true;
    const reason = ["cancel", "timeout", "overflow"].includes(
      this.stopReason ?? "",
    )
      ? this.stopReason
      : "close";
    void this.send(
      { type: "stop", reason, deadline: this.mapped(this.stopDeadline) },
      this.stopDeadline,
    ).catch((error: unknown) => {
      this.failure ??=
        error instanceof Error ? error : new Error("Process owner stop failed");
      this.control.end();
    });
  }

  close(): Promise<void> {
    if (!this.closing) {
      this.requestStop("close");
      this.closing = this.result.then(() => {});
    }
    return this.closing;
  }

  private finish(expired = false): void {
    if (this.settled || (!expired && !this.helperClosed)) return;
    this.settled = true;
    for (const timer of this.timers) clearTimeout(timer);
    this.options.signal?.removeEventListener("abort", this.abort);
    const terminal = this.terminal;
    const acquired = this.startSubmitted;
    const complete =
      terminal &&
      terminal.leaderReaped &&
      terminal.groupState === "quiescent" &&
      terminal.errors.length === 0 &&
      this.helperCode === 0 &&
      this.helperClosed;
    const noTarget = !acquired || this.refused;
    if (!complete && !noTarget)
      this.failure ??= new Error(
        `Subprocess cleanup could not be confirmed: ${terminal?.errors.join(", ") || "missing owner evidence"}`,
      );
    if (expired) this.failure ??= new Error("Subprocess cleanup timed out");
    if (!this.pid)
      this.started.reject(
        this.failure ?? new Error("Process owner did not start a target"),
      );
    this.helper.stdin?.destroy();
    this.stdout.destroy();
    this.stderr.destroy();
    this.control.destroy();
    this.helper.unref();
    if (this.failure) this.completion.reject(this.failure);
    else
      this.completion.resolve(
        terminal ?? {
          status: null,
          reason: "no-target",
          leaderReaped: true,
          groupState: "quiescent",
          errors: [],
        },
      );
  }
}

export async function startProcess(
  program: string,
  args: readonly string[],
  options: CommandOptions = {},
): Promise<OwnedProcess> {
  const entered = performance.now();
  options.signal?.throwIfAborted();
  const owner = new ProcessOwner(program, args, options, entered);
  try {
    await owner.started.promise;
    options.signal?.throwIfAborted();
    return owner;
  } catch (error) {
    const primary = options.signal?.aborted ? options.signal.reason : error;
    try {
      await owner.close();
    } catch (cleanup) {
      if (cleanup !== primary)
        throw new AggregateError(
          [primary, cleanup],
          "Subprocess startup and cleanup failed",
        );
    }
    throw primary;
  }
}

export function stopProcess(child: OwnedProcess): Promise<void> {
  if (!owned.has(child))
    return Promise.reject(new Error("Process handle is not an owned process"));
  let result = stopped.get(child);
  if (!result) {
    result = child.close().then(async () => {
      const outcome = await child.result;
      if (outcome.reason === "target-exit" && outcome.status !== 0)
        throw new Error(`Backend exited ${outcome.status} before cleanup`);
    });
    stopped.set(child, result);
  }
  return result;
}

export async function command(
  program: string,
  args: readonly string[],
  options: CommandOptions = {},
): Promise<CommandResult> {
  const child = await startProcess(program, args, options);
  const capture = child.capture;
  const limit = options.maxOutputBytes ?? 16 * 1024 * 1024;
  let failure: unknown;
  try {
    const result = await child.result;
    if (child.stopReason === "timeout") throw new Error(`${program} timed out`);
    if (child.stopReason === "cancel") options.signal?.throwIfAborted();
    if (capture.overflow)
      throw new Error(`${program} exceeded its ${limit}-byte output budget`);
    options.signal?.throwIfAborted();
    if (result.status !== 0)
      throw new Error(
        `${program} exited ${result.status}\n${capture.output.slice(-5000)}`,
      );
  } catch (error) {
    failure =
      child.stopReason === "timeout"
        ? new Error(`${program} timed out`, { cause: error })
        : child.stopReason === "cancel" && options.signal?.aborted
          ? options.signal.reason
          : capture.overflow
            ? new Error(`${program} exceeded its ${limit}-byte output budget`, {
                cause: error,
              })
            : options.signal?.aborted
              ? options.signal.reason
              : error;
  }
  const errors: unknown[] = [];
  if (failure !== undefined) errors.push(failure);
  try {
    await child.close();
  } catch (error) {
    if (error !== failure) errors.push(error);
  }
  if (options.log) {
    try {
      await mkdir(dirname(options.log), { recursive: true });
      await writeFile(options.log, capture.output);
    } catch (error) {
      errors.push(error);
    }
  }
  if (errors.length === 1) throw errors[0];
  if (errors.length)
    throw new AggregateError(errors, "Execution and cleanup failed");
  return { stdout: capture.stdout, output: capture.output };
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
