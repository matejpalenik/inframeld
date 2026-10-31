/** Keep native browser cleanup authority outside the test workers it observes. */
import type { BrowserServer } from "playwright";
import { chmod, mkdir, mkdtemp, open, rm, writeFile } from "node:fs/promises";
import { constants } from "node:fs";
import { createHash, randomBytes } from "node:crypto";
import type { Socket } from "node:net";
import type { TestContext } from "node:test";
import http from "node:http";
import { syncBuiltinESMExports } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { artifacts, cache, home } from "../../../src/config.ts";
import { command, withResources } from "../../../src/system/process.ts";
import { budgets } from "../../../src/system/budgets.ts";

export interface FixtureChannel {
  onData(receive: (bytes: Uint8Array) => void): void;
  onEnd(receive: () => void): void;
  write(bytes: Uint8Array): Promise<void>;
  end(): void;
}

export interface FixtureClock {
  now(): number;
  set(milliseconds: number, action: () => void): unknown;
  clear(timer: unknown): void;
}

export type FixtureDiagnosticScope = "broker" | "assertion" | "worker";
export type FixtureCaptureSlot = "probe" | "controller" | "timeout";
export interface FixtureCaptureMetadata {
  bytes: number;
  device: number;
  inode: number;
}
export interface FixtureCapture {
  path: string;
  check(deadline: number): Promise<FixtureCaptureMetadata>;
}

export function fixtureCaptureMetadata(
  initial: FixtureCaptureMetadata,
  current: FixtureCaptureMetadata,
): FixtureCaptureMetadata {
  if (
    ![
      initial.bytes,
      initial.device,
      initial.inode,
      current.bytes,
      current.device,
      current.inode,
    ].every((value) => Number.isSafeInteger(value) && value >= 0) ||
    current.bytes > 64 * 1024 * 1024 ||
    current.device !== initial.device ||
    current.inode !== initial.inode
  )
    throw new Error("Invalid protected capture");
  return { ...current };
}

/** Publish fixed facts only. Captured text and original errors stay protected. */
export function fixtureDiagnostic(value: unknown): string {
  const invalid = () => {
    throw new Error("Invalid fixture diagnostic");
  };
  if (
    !value ||
    typeof value !== "object" ||
    ![Object.prototype, null].includes(Object.getPrototypeOf(value))
  )
    return invalid();
  const fields = Object.getOwnPropertyDescriptors(value);
  const allowed = [
    "phase",
    "category",
    "status",
    "peer",
    "caseId",
    "slot",
    "bytes",
    "device",
    "inode",
  ];
  if (
    Object.entries(fields).some(
      ([key, field]) => !allowed.includes(key) || !("value" in field),
    )
  )
    return invalid();
  const row = value as Record<string, unknown>;
  if (
    typeof row.phase !== "string" ||
    typeof row.category !== "string" ||
    ![
      "probe-controller",
      "native-controller",
      "nested-controller",
      "peer-lost",
      "startup",
      "ready",
      "shutdown-observed",
      "finalize-started",
      "fixture-close-settled",
      "backend-outcome-settled",
      "browser-receipt-settled",
      "cleanup-report-written",
      "timeout-assertion",
      "receipt-read",
      "receipt-match",
      "assertion-finally",
      "fixture-terminal",
    ].includes(row.phase) ||
    ![
      "started",
      "passed",
      "failed",
      "cancelled",
      "unknown",
      "capture-unproved",
      "capture-checked",
      "capture-invalid",
      "diagnostic-failed",
      "cleanup-failed",
      "expected-close-deadline",
      "owner-unknown",
    ].includes(row.category)
  )
    return invalid();
  const record: Record<string, unknown> = {
    phase: row.phase,
    category: row.category,
    status: row.status ?? null,
  };
  if (
    record.status !== null &&
    (!Number.isSafeInteger(record.status) ||
      Number(record.status) < 0 ||
      Number(record.status) > 255)
  )
    return invalid();
  for (const key of ["peer", "caseId", "slot"]) {
    if (!(key in row)) continue;
    const choices =
      key === "peer"
        ? ["supervisor", "profile", "unbound"]
        : key === "slot"
          ? ["probe", "controller", "timeout"]
          : [
              "worker-loss",
              "startup-cancel",
              "stalled-close",
              "profile-timeout",
            ];
    if (typeof row[key] !== "string" || !choices.includes(row[key]))
      return invalid();
    record[key] = row[key];
  }
  for (const key of ["bytes", "device", "inode"]) {
    if (!(key in row)) continue;
    if (!Number.isSafeInteger(row[key]) || Number(row[key]) < 0)
      return invalid();
    record[key] = row[key];
  }
  return JSON.stringify(record) + "\n";
}

export class FixtureDiagnostics {
  private readonly records: string[] = [];
  private deadline: number | undefined;
  private writing: Promise<void> | undefined;
  constructor(readonly scope: FixtureDiagnosticScope) {}
  note(value: unknown): void {
    const record = fixtureDiagnostic(value);
    const limit = this.scope === "broker" ? 8192 : 4096;
    if (
      this.records.length >= 32 ||
      Buffer.byteLength(
        "[" +
          [...this.records, record].map((line) => line.trim()).join(",") +
          "]\n",
      ) > limit
    )
      throw new Error("Fixture diagnostic limit exceeded");
    this.records.push(record);
  }
  snapshot(): string {
    return "[" + this.records.map((line) => line.trim()).join(",") + "]\n";
  }
  async write(
    folder: string,
    deadline: number,
    clock: FixtureClock = browserFixtureClock,
    writer: (path: string, bytes: string) => Promise<void> = async (
      path,
      bytes,
    ) => {
      await writeFile(path, bytes, { mode: 0o600 });
    },
  ): Promise<void> {
    this.deadline = Math.min(this.deadline ?? deadline, deadline);
    const bytes = this.snapshot();
    this.writing = (this.writing ?? Promise.resolve()).then(() =>
      admit(
        clock,
        () => writer(join(folder, this.scope + "-status.json"), bytes),
        this.deadline!,
        "report",
      ),
    );
    return this.writing;
  }
}

export async function prepareFixtureCapture(
  folder: string,
  slot: FixtureCaptureSlot,
  deadline: number,
  clock: FixtureClock = browserFixtureClock,
): Promise<FixtureCapture> {
  if (!["probe", "controller", "timeout"].includes(slot))
    throw new Error("Invalid protected capture");
  if (clock.now() >= deadline) throw new FixtureDeadline("capture-deadline");
  const path = join(folder, slot + ".raw.log");
  const created = await open(path, "wx", 0o600);
  const initial = await withResources(
    async () => {
      const status = await created.stat();
      if (!status.isFile() || (status.mode & 0o777) !== 0o600)
        throw new Error("Invalid protected capture");
      return fixtureCaptureMetadata(
        { bytes: status.size, device: status.dev, inode: status.ino },
        { bytes: status.size, device: status.dev, inode: status.ino },
      );
    },
    () => created.close(),
  );
  let checking: Promise<FixtureCaptureMetadata> | undefined;
  return {
    path,
    check(end) {
      return (checking ??= admit(
        clock,
        async () => {
          const file = await open(
            path,
            constants.O_RDONLY | constants.O_NOFOLLOW,
          );
          return withResources(
            async () => {
              const status = await file.stat();
              if (!status.isFile() || (status.mode & 0o777) !== 0o600)
                throw new Error("Invalid protected capture");
              return fixtureCaptureMetadata(initial, {
                bytes: status.size,
                device: status.dev,
                inode: status.ino,
              });
            },
            () => file.close(),
          );
        },
        end,
        "capture",
      ));
    },
  };
}

export async function observeFixtureController<T>(
  diagnostics: FixtureDiagnostics,
  phase: "probe-controller" | "native-controller" | "nested-controller",
  work: () => Promise<T>,
): Promise<T> {
  let value!: T,
    failure: unknown,
    failed = false;
  try {
    value = await work();
  } catch (error) {
    failure = error;
    failed = true;
  }
  try {
    diagnostics.note({
      phase,
      category: failed ? "failed" : "passed",
      status: failed ? null : 0,
    });
  } catch (error) {
    if (failed)
      throw new AggregateError(
        [failure, error],
        "Controller and diagnostic recording failed",
      );
    throw error;
  }
  if (failed) throw failure;
  return value;
}

export interface BrowserLease {
  api: Pick<BrowserServer, "wsEndpoint" | "close" | "kill">;
  closed: Promise<void>;
}

export interface BrowserOwnerOptions {
  diagnostics?: FixtureDiagnostics;
  nonce: string;
  caseNonce(): string;
  clock: FixtureClock;
  launch(options: {
    channel: "chromium";
    headless: true;
    timeout: number;
  }): Promise<BrowserLease>;
  acquired?(caseId: string): void;
  failed?(caseId: string): void;
}

export interface BrowserOwnerReceipt {
  ownerId: string;
  requestId: number;
  caseId: string;
  operation: "close" | "kill";
  origin: "profile" | "emergency";
  fulfilled: boolean;
  closeObserved: boolean;
  completed: number;
}

export interface BrowserFixtureClient {
  nonce: string;
  completion: Promise<BrowserOwnerReceipt>;
  launch(options: {
    channel: "chromium";
    headless: true;
    timeout: number;
  }): Promise<BrowserLease["api"]>;
  end(): void;
}

export interface BrowserClientOptions {
  caseId: string;
  nonce: string;
  role?: "supervisor" | "profile";
  clock: FixtureClock;
  workDeadline: number;
  assertDeadline: number;
  channel?: FixtureChannel;
  socketPath?: string;
}

export const stalledCloseMessages = [
  `Error: Operation exceeded its ${budgets.resourceCleanup / 2}ms deadline`,
  "Error: close-deadline",
] as const;

/** Only the deliberate browser stall is expected. Independent shutdown failures remain fatal. */
export function expectedStalledCloseFailure(error: unknown): boolean {
  if (
    !(error instanceof AggregateError) ||
    error.message !== "Profile cleanup failed" ||
    error.cause !== undefined ||
    Object.keys(error).length ||
    error.errors.length !== 1
  )
    return false;
  const single: unknown = error.errors[0];
  if (
    !(single instanceof Error) ||
    single instanceof AggregateError ||
    single.cause !== undefined
  )
    return false;
  if (
    Object.keys(single).some(
      (key) =>
        key !== "code" ||
        (single as Error & { code?: unknown }).code !== "close-deadline",
    )
  )
    return false;
  return stalledCloseMessages.some((message) => String(single) === message);
}

export async function superviseBrowserWorker(
  owner: BrowserFixtureOwner,
  work: (signal: AbortSignal) => Promise<void>,
  report: (deadline: number) => Promise<void>,
  clock: FixtureClock,
  signal?: AbortSignal,
): Promise<void> {
  const controller = new AbortController(),
    stopping = waiting<void>(),
    worker = waiting<void>();
  const errors: unknown[] = [];
  let deadline: number | undefined,
    cleanup: Promise<void> | undefined,
    boundedWorker: Promise<void> | undefined;
  const begin = (reason?: unknown) => {
    if (reason !== undefined && !errors.includes(reason)) errors.push(reason);
    if (deadline !== undefined) return;
    deadline = clock.now() + 10000;
    controller.abort(reason ?? new Error("Browser worker finished"));
    cleanup = owner.stop(deadline);
    void cleanup.catch(() => {});
    boundedWorker = bound(clock, worker.promise, deadline, "worker");
    void boundedWorker.catch(() => {});
    stopping.resolve();
  };
  const interrupt = () =>
    begin(signal?.reason ?? new Error("Browser worker interrupted"));
  signal?.addEventListener("abort", interrupt, { once: true });
  if (signal?.aborted) interrupt();
  void Promise.resolve()
    .then(() => work(controller.signal))
    .then(worker.resolve, worker.reject);
  try {
    try {
      await Promise.race([
        worker.promise,
        stopping.promise.then(() => boundedWorker!),
      ]);
    } catch (error) {
      if (!errors.includes(error)) errors.push(error);
    }
    begin();
    try {
      await cleanup;
    } catch (error) {
      if (!errors.includes(error)) errors.push(error);
    }
    try {
      await admit(clock, () => report(deadline!), deadline!, "report");
    } catch (error) {
      errors.push(error);
    }
  } finally {
    signal?.removeEventListener("abort", interrupt);
  }
  if (errors.length === 1) throw errors[0];
  if (errors.length)
    throw new AggregateError(errors, "Browser worker and cleanup failed");
}

function waiting<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  void promise.catch(() => {});
  return { promise, resolve, reject };
}

function socketChannel(socket: Socket): FixtureChannel {
  return {
    onData(receive) {
      socket.on("data", receive);
    },
    onEnd(receive) {
      socket.once("end", receive);
      socket.once("close", receive);
      socket.once("error", receive);
    },
    write(bytes) {
      return new Promise<void>((resolve, reject) =>
        socket.write(bytes, (error) => (error ? reject(error) : resolve())),
      );
    },
    end() {
      socket.destroy();
    },
  };
}

export async function connectBrowserCase(
  options: BrowserClientOptions,
): Promise<BrowserFixtureClient> {
  const clock = options.clock;
  const handshakeDeadline = Math.min(options.workDeadline, clock.now() + 2000);
  let channel = options.channel;
  if (!channel) {
    if (
      !options.socketPath ||
      !options.socketPath.startsWith("/") ||
      Buffer.byteLength(options.socketPath) >= 100
    )
      throw new Error("Invalid browser fixture socket path");
    const { connect } = await import("node:net");
    if (clock.now() >= handshakeDeadline)
      throw new FixtureDeadline("control-deadline");
    const socket = connect(options.socketPath);
    try {
      await bound(
        clock,
        new Promise<void>((resolve, reject) => {
          socket.once("connect", resolve);
          socket.once("error", reject);
        }),
        handshakeDeadline,
        "control",
      );
    } catch (error) {
      socket.destroy();
      throw error;
    }
    channel = socketChannel(socket);
  }
  const transport = channel;
  const ready = waiting<{ caseNonce: string }>(),
    armed = waiting<void>(),
    evidence = waiting<BrowserOwnerReceipt>();
  const completion = bound(
    clock,
    evidence.promise,
    options.assertDeadline,
    "owner-evidence",
  );
  void completion.catch(() => {});
  const requests = new Map<
    number,
    { op: string; reply: ReturnType<typeof waiting<Record<string, unknown>>> }
  >();
  const retired = new Map<number, string>();
  let buffer = Buffer.alloc(0),
    total = 0,
    frames = 0,
    sequence = 0;
  let nonce = "",
    closed = false,
    didArm = false;
  const drop = (error: unknown) => {
    if (closed) return;
    closed = true;
    ready.reject(error);
    armed.reject(error);
    evidence.reject(error);
    for (const request of requests.values()) request.reply.reject(error);
    requests.clear();
    transport.end();
  };
  const receipt = (raw: unknown): BrowserOwnerReceipt => {
    if (!raw || typeof raw !== "object" || Array.isArray(raw))
      throw new Error("Invalid browser owner receipt");
    const r = raw as Record<string, unknown>;
    if (
      Object.keys(r).sort().join() !==
        "caseId,closeObserved,completed,fulfilled,operation,origin,ownerId,requestId" ||
      r.caseId !== options.caseId ||
      r.ownerId !== createHash("sha256").update(nonce).digest("hex") ||
      r.origin !== "profile" ||
      r.fulfilled !== true ||
      r.closeObserved !== true ||
      !["close", "kill"].includes(String(r.operation)) ||
      integer(r.requestId) <= 0 ||
      !Number.isFinite(r.completed) ||
      clock.now() >= options.assertDeadline
    )
      throw new Error("Unconfirmed browser owner receipt");
    return r as unknown as BrowserOwnerReceipt;
  };
  transport.onData((chunk) => {
    if (closed) return;
    total += chunk.length;
    try {
      if (buffer.length + chunk.length > 8192 || total > 64 * 1024)
        throw new Error("Browser owner input limit");
      buffer = Buffer.concat([buffer, chunk]);
      let boundary: number;
      while ((boundary = buffer.indexOf(10)) >= 0) {
        if (boundary > 4096 || ++frames > 8)
          throw new Error("Browser owner frame limit");
        const value = document(buffer.subarray(0, boundary));
        buffer = buffer.subarray(boundary + 1);
        if (value.type === "ready") {
          keys(value, "clock", "caseNonce");
          timestamp(value.clock);
          if (
            nonce ||
            typeof value.caseNonce !== "string" ||
            value.caseNonce.length > 128
          )
            throw new Error("Invalid browser owner READY");
          nonce = value.caseNonce;
          ready.resolve({ caseNonce: nonce });
        } else if (value.type === "armed") {
          keys(value);
          if (!nonce || didArm)
            throw new Error("Invalid browser owner ARM state");
          didArm = true;
          armed.resolve();
        } else if (value.type === "receipt") {
          keys(value, "receipt");
          if (!didArm)
            throw new Error("Browser owner evidence arrived before case armed");
          evidence.resolve(receipt(value.receipt));
        } else if (value.type === "reply") {
          const id = integer(value.id),
            request = requests.get(id);
          if (
            !didArm ||
            typeof value.ok !== "boolean" ||
            (request?.op ?? retired.get(id)) !== value.op
          )
            throw new Error("Invalid browser owner reply");
          if (!value.ok) {
            keys(value, "id", "op", "ok", "error");
            if (typeof value.error !== "string")
              throw new Error("Invalid browser owner error");
            request?.reply.reject(new Error(value.error));
          } else if (value.op === "launch") {
            keys(value, "id", "op", "ok", "endpoint");
            if (
              typeof value.endpoint !== "string" ||
              value.endpoint.length > 2048
            )
              throw new Error("Invalid browser endpoint");
            request?.reply.resolve(value);
          } else {
            keys(value, "id", "op", "ok", "receipt");
            const proof = receipt(value.receipt);
            if (proof.requestId !== id || proof.operation !== value.op)
              throw new Error("Mismatched browser receipt");
            if (request) {
              evidence.resolve(proof);
              request.reply.resolve(value);
            }
          }
          requests.delete(id);
        } else throw new Error("Unknown browser owner frame");
      }
    } catch (error) {
      buffer = Buffer.alloc(0);
      drop(error);
    }
  });
  transport.onEnd(() =>
    drop(
      new Error(
        buffer.length
          ? "Browser owner control truncated"
          : "Browser owner control lost",
      ),
    ),
  );
  const send = async (value: object, deadline: number) => {
    if (closed) throw new Error("Browser owner control closed");
    if (clock.now() >= deadline) throw new FixtureDeadline("control-deadline");
    const bytes = Buffer.from(JSON.stringify({ version: 1, ...value }) + "\n");
    if (bytes.length > 4096) throw new Error("Browser owner request size");
    await bound(
      clock,
      transport.write(bytes),
      Math.min(deadline, clock.now() + 2000),
      "control",
    );
  };
  try {
    await send(
      {
        type: "hello",
        nonce: options.nonce,
        role: options.role ?? "supervisor",
        caseId: options.caseId,
      },
      handshakeDeadline,
    );
    await bound(clock, ready.promise, handshakeDeadline, "control");
    const readyAt = clock.now();
    await send(
      {
        type: "arm",
        readyAt,
        sent: clock.now(),
        workDeadline: options.workDeadline,
        assertDeadline: options.assertDeadline,
      },
      handshakeDeadline,
    );
    await bound(clock, armed.promise, handshakeDeadline, "control");
  } catch (error) {
    drop(error);
    throw error;
  }
  let launch: Promise<BrowserLease["api"]> | undefined;
  let browserDeadline: number | undefined;
  const transact = async (
    op: string,
    deadline: number,
    launchOptions?: object,
  ) => {
    if (closed) throw new Error("Browser owner control closed");
    const id = ++sequence,
      reply = waiting<Record<string, unknown>>();
    requests.set(id, { op, reply });
    try {
      await send(
        {
          type: "request",
          id,
          op,
          nonce,
          deadline,
          ...(launchOptions ? { options: launchOptions } : {}),
        },
        deadline,
      );
      return await bound(clock, reply.promise, deadline, op);
    } finally {
      retired.set(id, op);
      requests.delete(id);
    }
  };
  return {
    nonce,
    completion,
    launch(launchOptions) {
      if (!launch)
        launch = transact(
          "launch",
          Math.min(options.workDeadline, clock.now() + launchOptions.timeout),
          {
            ...launchOptions,
            timeout: Math.max(1, Math.floor(launchOptions.timeout)),
          },
        ).then((value) => {
          const calls = new Map<"close" | "kill", Promise<void>>();
          const call = (op: "close" | "kill") => {
            let result = calls.get(op);
            if (!result) {
              browserDeadline ??= Math.min(
                options.assertDeadline,
                clock.now() + 5000,
              );
              result = transact(
                op,
                Math.min(browserDeadline, clock.now() + 2500),
              ).then(() => {});
              calls.set(op, result);
            }
            return result;
          };
          return {
            wsEndpoint: () => value.endpoint as string,
            close: () => call("close"),
            kill: () => call("kill"),
          };
        });
      return launch;
    },
    end() {
      drop(new Error("Browser owner client closed"));
    },
  };
}

export interface BrowserOwnerCase {
  id: string;
  state: "idle" | "launching" | "live" | "closed" | "unknown";
  emergency: boolean;
  recoveryDeadline: number | null;
  held: boolean;
  instrumentation: "native" | "close-injected-stall";
  errors: string[];
  receipts: BrowserOwnerReceipt[];
}

const caseCaps: Record<string, number> = {
  "startup-cancel": 30000,
  "stalled-close": 30000,
  "profile-timeout": 10000,
  "worker-loss": 10000,
};
const stallCases = new Set(["stalled-close", "profile-timeout"]);

class FixtureDeadline extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

function keys(value: Record<string, unknown>, ...names: string[]): void {
  if (
    Object.keys(value).sort().join() !==
    ["version", "type", ...names].sort().join()
  )
    throw new Error("invalid-fields");
}
function integer(value: unknown): number {
  if (!Number.isSafeInteger(value)) throw new Error("invalid-clock");
  return value as number;
}
function timestamp(value: unknown): number {
  if (
    typeof value !== "number" ||
    !Number.isFinite(value) ||
    Math.abs(value) > Number.MAX_SAFE_INTEGER
  )
    throw new Error("invalid-clock");
  return value;
}
function document(bytes: Uint8Array): Record<string, unknown> {
  const text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  const value: unknown = JSON.parse(text);
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    JSON.stringify(value) !== text
  )
    throw new Error("invalid-document");
  const result = value as Record<string, unknown>;
  if (result.version !== 1) throw new Error("invalid-version");
  return result;
}
function bound<T>(
  clock: FixtureClock,
  promise: Promise<T>,
  deadline: number,
  phase: string,
): Promise<T> {
  if (clock.now() >= deadline)
    return Promise.reject(new FixtureDeadline(`${phase}-deadline`));
  return new Promise<T>((resolve, reject) => {
    const timer = clock.set(deadline - clock.now(), () =>
      reject(new FixtureDeadline(`${phase}-deadline`)),
    );
    promise
      .then(
        (value) =>
          clock.now() >= deadline
            ? reject(new FixtureDeadline(`${phase}-deadline`))
            : resolve(value),
        reject,
      )
      .finally(() => clock.clear(timer));
  });
}

function admit<T>(
  clock: FixtureClock,
  effect: () => Promise<T>,
  deadline: number,
  phase: string,
): Promise<T> {
  if (clock.now() >= deadline)
    return Promise.reject(new FixtureDeadline(`${phase}-deadline`));
  try {
    return bound(clock, effect(), deadline, phase);
  } catch (error) {
    return Promise.reject(error);
  }
}

class OwnedBrowserCase {
  readonly row: BrowserOwnerCase;
  readonly peers = new Set<OwnerPeer>();
  workDeadline = 0;
  assertDeadline = 0;
  received = 0;
  private assertionTimer: unknown;
  private launchPromise: Promise<BrowserLease> | undefined;
  private admitted = false;
  private lease: BrowserLease | undefined;
  private endpoint: string | undefined;
  private closedObserved = false;
  private readonly apiCalls = new Map<"close" | "kill", Promise<void>>();
  private browserDeadline: number | undefined;
  private recovery: Promise<void> | undefined;

  constructor(
    readonly owner: BrowserFixtureOwner,
    readonly id: string,
    readonly nonce: string,
  ) {
    this.row = {
      id,
      state: "idle",
      emergency: false,
      recoveryDeadline: null,
      held: false,
      instrumentation: stallCases.has(id) ? "close-injected-stall" : "native",
      errors: [],
      receipts: [],
    };
  }

  arm(work: number, assertion: number, recoveryAt: number): void {
    if (this.assertDeadline) return;
    this.workDeadline = work;
    this.assertDeadline = assertion;
    this.assertionTimer = this.owner.options.clock.set(
      Math.max(0, recoveryAt - this.owner.options.clock.now()),
      () => this.fail("case-deadline"),
    );
  }
  error(code: string): void {
    if (!this.row.errors.includes(code) && this.row.errors.length < 16)
      this.row.errors.push(code);
  }
  fail(code: string): void {
    this.error(code);
    this.owner.options.failed?.(this.id);
    void this.recover(this.owner.options.clock.now() + 5000).catch(() => {});
  }
  async launch(deadline: number, timeout: number): Promise<string> {
    if (
      this.launchPromise ||
      this.row.emergency ||
      !this.workDeadline ||
      this.owner.busy(this.id)
    )
      throw new Error("launch-state");
    const clock = this.owner.options.clock;
    deadline = Math.min(deadline, this.workDeadline);
    if (deadline <= clock.now()) throw new FixtureDeadline("launch-deadline");
    this.row.state = "launching";
    this.row.held = true;
    this.launchPromise = Promise.resolve()
      .then(() => {
        if (this.row.emergency || clock.now() >= deadline)
          throw new FixtureDeadline("launch-deadline");
        this.admitted = true;
        return this.owner.options.launch({
          channel: "chromium",
          headless: true,
          timeout: Math.min(timeout, deadline - clock.now()),
        });
      })
      .then(
        (lease) => {
          this.lease = lease;
          this.row.state =
            this.row.emergency &&
            clock.now() >= (this.row.recoveryDeadline ?? 0)
              ? "unknown"
              : "live";
          void lease.closed.then(() => {
            this.closedObserved = true;
          });
          this.owner.options.acquired?.(this.id);
          return lease;
        },
        (error: unknown) => {
          this.row.state = this.admitted ? "unknown" : "closed";
          this.row.held = this.admitted;
          if (!this.admitted) clock.clear(this.assertionTimer);
          this.error("launch-failed");
          throw error;
        },
      );
    void this.launchPromise.catch(() => {});
    try {
      const lease = await bound(clock, this.launchPromise, deadline, "launch");
      if (this.row.emergency) throw new Error("emergency-started");
      this.endpoint = lease.api.wsEndpoint();
      return this.endpoint;
    } catch (error) {
      this.error(
        error instanceof FixtureDeadline ? error.code : "launch-failed",
      );
      throw error;
    }
  }
  privateText(): string[] {
    return [this.nonce, ...(this.endpoint ? [this.endpoint] : [])];
  }
  private actual(operation: "close" | "kill", deadline: number): Promise<void> {
    let result = this.apiCalls.get(operation);
    if (!result) {
      if (!this.lease)
        return Promise.reject(new Error("missing-browser-owner"));
      const lease = this.lease;
      result =
        operation === "close" && stallCases.has(this.id)
          ? new Promise<void>(() => {})
          : Promise.resolve().then(() => {
              if (this.owner.options.clock.now() >= deadline)
                throw new FixtureDeadline(`${operation}-deadline`);
              return lease.api[operation]();
            });
      result = Promise.all([result, lease.closed]).then(() => {});
      void result.catch(() => {});
      this.apiCalls.set(operation, result);
    }
    return result;
  }
  async operation(
    operation: "close" | "kill",
    deadline: number,
    requestId: number,
  ): Promise<BrowserOwnerReceipt> {
    const clock = this.owner.options.clock;
    if (!this.lease || this.row.emergency) throw new Error("owner-unavailable");
    this.browserDeadline ??= Math.min(clock.now() + 5000, this.assertDeadline);
    deadline = Math.min(deadline, clock.now() + 2500, this.browserDeadline);
    try {
      await admit(
        clock,
        () => this.actual(operation, deadline),
        deadline,
        operation,
      );
      if (this.row.emergency || clock.now() >= deadline)
        throw new FixtureDeadline(`${operation}-deadline`);
      const receipt: BrowserOwnerReceipt = {
        ownerId: createHash("sha256").update(this.nonce).digest("hex"),
        requestId,
        caseId: this.id,
        operation,
        origin: "profile",
        fulfilled: true,
        closeObserved: this.closedObserved,
        completed: clock.now(),
      };
      this.row.state = "closed";
      this.row.held = false;
      clock.clear(this.assertionTimer);
      this.row.receipts.push(receipt);
      return receipt;
    } catch (error) {
      this.error(
        error instanceof FixtureDeadline ? error.code : `${operation}-failed`,
      );
      throw error;
    }
  }
  recover(limit: number): Promise<void> {
    if (this.recovery) return this.recovery;
    if (this.row.state === "closed") return Promise.resolve();
    const clock = this.owner.options.clock;
    this.row.emergency = true;
    this.row.recoveryDeadline = Math.min(clock.now() + 5000, limit);
    clock.clear(this.assertionTimer);
    this.recovery = (async () => {
      if (!this.launchPromise) {
        this.row.state = "closed";
        this.row.held = false;
        return;
      }
      try {
        await bound(
          clock,
          this.launchPromise,
          this.row.recoveryDeadline!,
          "recovery",
        );
        if (clock.now() >= this.row.recoveryDeadline!)
          throw new FixtureDeadline("recovery-deadline");
        await admit(
          clock,
          () => this.actual("kill", this.row.recoveryDeadline!),
          this.row.recoveryDeadline!,
          "recovery",
        );
        this.row.state = "closed";
        this.row.held = false;
        this.row.receipts.push({
          ownerId: createHash("sha256").update(this.nonce).digest("hex"),
          requestId: 0,
          caseId: this.id,
          operation: "kill",
          origin: "emergency",
          fulfilled: true,
          closeObserved: this.closedObserved,
          completed: clock.now(),
        });
      } catch (error) {
        if (!this.admitted) {
          this.row.state = "closed";
          this.row.held = false;
          return;
        }
        this.row.state = "unknown";
        this.row.held = true;
        this.error(
          error instanceof FixtureDeadline ? error.code : "recovery-failed",
        );
        throw new Error("Browser ownership remains unknown", { cause: error });
      }
    })();
    void this.recovery.catch(() => {});
    return this.recovery;
  }
}

interface OwnerPeer {
  channel: FixtureChannel;
  role?: "supervisor" | "profile";
  browser?: OwnedBrowserCase;
  anchor?: { owner: number; client: number };
  send(value: object, deadline?: number): Promise<void>;
}

export class BrowserFixtureOwner {
  private readonly lostPeers = new Set<string>();
  private readonly cases = new Map<string, OwnedBrowserCase>();
  private readonly errors: string[] = [];
  private total = 0;
  private accepted = 0;
  constructor(readonly options: BrowserOwnerOptions) {}

  redact(text: string): string {
    for (const value of [
      this.options.nonce,
      ...[...this.cases.values()].flatMap((c) => c.privateText()),
    ])
      if (value) text = text.replaceAll(value, "<browser-fixture-private>");
    return text;
  }

  busy(id: string): boolean {
    return [...this.cases.values()].some((c) => c.id !== id && c.row.held);
  }

  accept(channel: FixtureChannel): void {
    let buffer = Buffer.alloc(0),
      frames = 0,
      id = 0;
    let received = 0;
    let alive = true;
    const clock = this.options.clock;
    const fail = (code: string) => {
      if (!alive) return;
      alive = false;
      if (this.errors.length < 16) this.errors.push(code);
      peer.browser?.peers.delete(peer);
      if (peer.browser?.row.held) peer.browser.fail(code);
      channel.end();
    };
    const peer: OwnerPeer = {
      channel,
      async send(value, deadline = clock.now() + 2000) {
        if (!alive) return;
        // An expired method reply has no remaining delivery allowance. The client
        // owns that same deadline and may still use the remaining kill phase.
        if (clock.now() >= deadline) return;
        const payload = Buffer.from(
          JSON.stringify({ version: 1, ...value }) + "\n",
        );
        if (payload.length > 4096) {
          fail("control-size");
          return;
        }
        try {
          await bound(
            clock,
            channel.write(payload),
            Math.min(deadline, clock.now() + 2000),
            "control",
          );
        } catch (error) {
          fail(
            error instanceof FixtureDeadline
              ? error.code
              : "control-write-failed",
          );
        }
      },
    };
    if (++this.accepted > 8) {
      fail("connection-limit");
      return;
    }
    const receive = (value: Record<string, unknown>) => {
      if (!peer.role) {
        keys(value, "nonce", "role", "caseId");
        if (
          value.type !== "hello" ||
          typeof value.caseId !== "string" ||
          !Object.hasOwn(caseCaps, value.caseId) ||
          !["supervisor", "profile"].includes(String(value.role))
        )
          throw new Error("invalid-hello");
        let browser = this.cases.get(value.caseId);
        if (value.role === "supervisor") {
          if (value.nonce !== this.options.nonce || browser)
            throw new Error("invalid-capability");
          browser = new OwnedBrowserCase(
            this,
            value.caseId,
            this.options.caseNonce(),
          );
          this.cases.set(value.caseId, browser);
        } else if (!browser || value.nonce !== browser.nonce)
          throw new Error("invalid-capability");
        if (!browser || browser.peers.size >= 2)
          throw new Error("connection-limit");
        peer.role = value.role as "supervisor" | "profile";
        peer.browser = browser;
        browser.received += received;
        if (browser.received > 64 * 1024) throw new Error("control-size");
        browser.peers.add(peer);
        peer.anchor = { owner: clock.now(), client: 0 };
        void peer.send({
          type: "ready",
          clock: peer.anchor.owner,
          caseNonce: browser.nonce,
        });
        return;
      }
      const browser = peer.browser!;
      if (!peer.anchor!.client) {
        keys(value, "readyAt", "sent", "workDeadline", "assertDeadline");
        const readyAt = timestamp(value.readyAt),
          sent = timestamp(value.sent),
          work = timestamp(value.workDeadline),
          assertion = timestamp(value.assertDeadline);
        if (
          value.type !== "arm" ||
          readyAt <= 0 ||
          sent < readyAt ||
          work <= sent ||
          assertion < work ||
          assertion - sent > caseCaps[browser.id]!
        )
          throw new Error("invalid-deadline");
        peer.anchor!.client = readyAt;
        if (peer.role === "supervisor")
          browser.arm(
            peer.anchor!.owner + work - readyAt,
            peer.anchor!.owner + assertion - readyAt,
            clock.now() + assertion - sent,
          );
        else if (!browser.assertDeadline) throw new Error("unarmed-case");
        void peer.send({ type: "armed" });
        return;
      }
      if (value.op === "launch")
        keys(value, "id", "op", "nonce", "deadline", "options");
      else keys(value, "id", "op", "nonce", "deadline");
      if (
        value.type !== "request" ||
        value.nonce !== browser.nonce ||
        integer(value.id) !== id + 1 ||
        id >= 3 ||
        !["launch", "close", "kill"].includes(String(value.op))
      )
        throw new Error("invalid-request");
      id++;
      const deadline = Math.min(
        peer.anchor!.owner + timestamp(value.deadline) - peer.anchor!.client,
        browser.assertDeadline,
      );
      let result: Promise<object>;
      if (value.op === "launch") {
        const opts = value.options;
        if (!opts || typeof opts !== "object" || Array.isArray(opts))
          throw new Error("invalid-launch");
        const options = opts as Record<string, unknown>;
        if (
          Object.keys(options).sort().join() !== "channel,headless,timeout" ||
          options.channel !== "chromium" ||
          options.headless !== true
        )
          throw new Error("invalid-launch");
        const timeout = integer(options.timeout);
        if (timeout <= 0) throw new Error("invalid-launch");
        result = browser
          .launch(deadline, timeout)
          .then((endpoint) => ({ endpoint }));
      } else {
        const operation = value.op as "close" | "kill";
        result = browser.operation(operation, deadline, id).then((receipt) => {
          for (const target of browser.peers)
            if (target.role === "supervisor")
              void target.send({ type: "receipt", receipt }, deadline);
          return { receipt };
        });
      }
      void result.then(
        (detail) =>
          peer.send(
            { type: "reply", id: value.id, op: value.op, ok: true, ...detail },
            deadline,
          ),
        (error: unknown) =>
          peer.send(
            {
              type: "reply",
              id: value.id,
              op: value.op,
              ok: false,
              error:
                error instanceof FixtureDeadline
                  ? error.code
                  : `${value.op}-failed`,
            },
            deadline,
          ),
      );
    };
    channel.onData((chunk) => {
      if (!alive) return;
      this.total += chunk.length;
      received += chunk.length;
      if (peer.browser) peer.browser.received += chunk.length;
      if (
        buffer.length + chunk.length > 8192 ||
        this.total > 256 * 1024 ||
        (peer.browser?.received ?? 0) > 64 * 1024
      ) {
        fail("control-size");
        return;
      }
      buffer = Buffer.concat([buffer, chunk]);
      let boundary: number;
      try {
        while ((boundary = buffer.indexOf(10)) >= 0) {
          if (boundary > 4096 || ++frames > 8) throw new Error("control-size");
          const bytes = buffer.subarray(0, boundary);
          buffer = buffer.subarray(boundary + 1);
          receive(document(bytes));
        }
      } catch (error) {
        buffer = Buffer.alloc(0);
        fail(
          error instanceof Error && /^[a-z-]{1,64}$/.test(error.message)
            ? error.message
            : "invalid-document",
        );
      }
    });
    channel.onEnd(() => {
      if (buffer.length) {
        fail("truncated-control");
        return;
      }
      if (!alive) return;
      alive = false;
      peer.browser?.peers.delete(peer);
      if (peer.browser?.row.held) {
        try {
          if (!this.lostPeers.has(peer.browser.id)) {
            this.lostPeers.add(peer.browser.id);
            this.options.diagnostics?.note({
              phase: "peer-lost",
              category: "failed",
              peer: peer.role ?? "unbound",
              caseId: peer.browser.id,
              status: null,
            });
          }
        } catch {
          if (this.errors.length < 16) this.errors.push("diagnostic-failed");
        } finally {
          peer.browser.fail("client-lost");
        }
      }
    });
  }

  snapshot(): { errors: string[]; cases: BrowserOwnerCase[] } {
    return {
      errors: [...this.errors],
      cases: [...this.cases.values()].map((c) => ({
        ...c.row,
        errors: [...c.row.errors],
        receipts: [...c.row.receipts],
      })),
    };
  }

  async stop(deadline: number): Promise<void> {
    const results = await Promise.allSettled(
      [...this.cases.values()]
        .filter((c) => c.row.state !== "closed")
        .map((c) => c.recover(deadline)),
    );
    if (
      results.some((r) => r.status === "rejected") ||
      [...this.cases.values()].some((c) => c.row.held)
    )
      throw new Error("Browser ownership remains unknown");
  }

  async writeReport(path: string): Promise<void> {
    try {
      const bytes = JSON.stringify(this.snapshot()) + "\n";
      if (Buffer.byteLength(bytes) > 256 * 1024) throw new Error("report-size");
      await writeFile(path, bytes);
    } catch (error) {
      if (this.errors.length < 16) this.errors.push("report-write-failed");
      throw error;
    }
  }
}

export const browserFixtureClock: FixtureClock = {
  now: () => performance.now(),
  set: (milliseconds, action) => setTimeout(action, milliseconds),
  clear: (timer) => clearTimeout(timer as ReturnType<typeof setTimeout>),
};

/** Fixture clients receive no process handle and can request only the three API calls. */
export function openBrowserCase(
  caseId: string,
  workDeadline: number,
  assertDeadline: number,
  role: "supervisor" | "profile" = "supervisor",
): Promise<BrowserFixtureClient> {
  const nonce =
    role === "profile"
      ? process.env.SDK_BROWSER_OWNER_CASE_CAP
      : process.env.SDK_BROWSER_OWNER_NONCE;
  if (!nonce || !process.env.SDK_BROWSER_OWNER_SOCKET)
    throw new Error(
      "Run browser resource cases through the browser-owner fixture launcher",
    );
  return connectBrowserCase({
    caseId,
    workDeadline,
    assertDeadline,
    role,
    nonce,
    socketPath: process.env.SDK_BROWSER_OWNER_SOCKET,
    clock: browserFixtureClock,
  });
}

/** Observe the actual profile listener's close event without adding a production port. */
export function observeProfileListener(context: TestContext): () => boolean {
  let acquired = false,
    closed = false;
  const create = http.createServer;
  context.mock.method(http, "createServer", ((
    ...args: Parameters<typeof create>
  ) => {
    const server = create(...args);
    acquired = true;
    server.once("close", () => {
      closed = true;
    });
    return server;
  }) as typeof create);
  syncBuiltinESMExports();
  context.after(() => {
    context.mock.restoreAll();
    syncBuiltinESMExports();
  });
  return () => acquired && closed;
}

/** Allocate a private short socket directory before admitting browser work. */
export async function acquireBrowserFixtureDirectory(
  create: (prefix: string) => Promise<string> = mkdtemp,
): Promise<{ folder: string; socketPath: string }> {
  // Keep Unix socket paths short on Linux and macOS, even with a long TMPDIR.
  const folder = await create("/tmp/im237b-");
  try {
    await chmod(folder, 0o700);
  } catch (error) {
    await rm(folder, { recursive: true, force: true });
    throw error;
  }
  const socketPath = join(folder, "b");
  if (Buffer.byteLength(socketPath) >= 100) {
    await rm(folder, { recursive: true, force: true });
    throw new Error("Invalid private browser fixture path");
  }
  return { folder, socketPath };
}

async function runFixture(mode: string): Promise<void> {
  if (!["profile", "native", "worker-loss-probe"].includes(mode))
    throw new Error("Unknown fixed browser fixture mode");
  const { createServer } = await import("node:net");
  const evidence =
    process.env.SDK_BROWSER_OWNER_EVIDENCE ||
    join(artifacts, "native-browser-owner.json");
  if (!evidence.startsWith("/"))
    throw new Error("Invalid private browser fixture path");
  await mkdir(dirname(evidence), { recursive: true });
  const protectedFolder = await mkdtemp(evidence + ".protected-");
  await chmod(protectedFolder, 0o700);
  const { folder, socketPath } = await acquireBrowserFixtureDirectory();
  const nonce = randomBytes(24).toString("hex");
  process.env.PLAYWRIGHT_BROWSERS_PATH ??= join(cache, "browsers");
  const root = new AbortController();
  let active: AbortController | undefined;
  let closing = false,
    workerCompleted = false,
    ipcCompleted = false;
  let stopDeadline: number | undefined;
  const probeFailure = new Error("Expected browser-only worker termination");
  const diagnostics = new FixtureDiagnostics("broker");
  const captures = new Map<FixtureCaptureSlot, FixtureCapture>();
  const owner = new BrowserFixtureOwner({
    diagnostics,
    nonce,
    caseNonce: () => randomBytes(24).toString("hex"),
    clock: browserFixtureClock,
    async launch(options) {
      const { chromium } = await import("playwright");
      const server = await chromium.launchServer(options);
      const closed = waiting<void>();
      server.once("close", () => closed.resolve());
      if (
        server.process().exitCode !== null ||
        server.process().signalCode !== null
      )
        closed.resolve();
      return { api: server, closed: closed.promise };
    },
    acquired(caseId) {
      if (caseId === "worker-loss") active?.abort(probeFailure);
    },
    failed(caseId) {
      active?.abort(new Error(`Browser fixture ${caseId} incomplete`));
    },
  });
  const sockets = new Set<Socket>();
  const server = createServer((socket) => {
    if (closing) {
      socket.destroy();
      return;
    }
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
    owner.accept(socketChannel(socket));
  });
  const interrupt = (signal: string) =>
    root.abort(new Error(`Browser fixture interrupted by ${signal}`));
  const term = () => interrupt("SIGTERM"),
    int = () => interrupt("SIGINT");
  process.once("SIGTERM", term);
  process.once("SIGINT", int);
  const errors: unknown[] = [];
  try {
    await bound(
      browserFixtureClock,
      new Promise<void>((resolve, reject) => {
        server.once("error", reject);
        server.listen(socketPath, resolve);
      }),
      performance.now() + 2000,
      "listener",
    );
    const loader = join(home, "node_modules/tsx/dist/loader.mjs");
    const env = {
      SDK_BROWSER_OWNER_SOCKET: socketPath,
      SDK_BROWSER_OWNER_NONCE: nonce,
      NODE_TEST_CONTEXT: undefined,
    };
    active = new AbortController();
    try {
      await superviseBrowserWorker(
        owner,
        async (signal) => {
          const began = performance.now();
          const capture = await prepareFixtureCapture(
            protectedFolder,
            "probe",
            began + 15000,
          );
          captures.set("probe", capture);
          await observeFixtureController(diagnostics, "probe-controller", () =>
            command(
              process.execPath,
              [
                "--import",
                loader,
                "--test",
                join(home, "tests/native/fixtures/timeout-profile.ts"),
              ],
              {
                signal,
                timeout: 15000,
                executionDeadline: began + 15000,
                cleanupTimeout: 5000,
                log: capture.path,
                env: { ...env, SDK_BROWSER_OWNER_PROBE: "1" },
              },
            ),
          );
        },
        (deadline) => {
          stopDeadline = deadline;
          return owner.writeReport(evidence);
        },
        browserFixtureClock,
        AbortSignal.any([root.signal, active.signal]),
      );
      throw new Error("Controlled browser worker unexpectedly succeeded");
    } catch (error) {
      const probe = owner.snapshot().cases.find((c) => c.id === "worker-loss");
      if (
        error !== probeFailure ||
        probe?.state !== "closed" ||
        probe.held ||
        !probe.receipts.some(
          (r) => r.origin === "emergency" && r.fulfilled && r.closeObserved,
        )
      )
        throw error;
    }
    if (mode !== "worker-loss-probe") {
      active = new AbortController();
      const files =
        mode === "native"
          ? ["driver.test.ts", "lifecycle.test.ts", "profile-resources.test.ts"]
          : ["profile-resources.test.ts"];
      await superviseBrowserWorker(
        owner,
        async (signal) => {
          const began = performance.now();
          const capture = await prepareFixtureCapture(
            protectedFolder,
            "controller",
            began + 900000,
          );
          captures.set("controller", capture);
          await observeFixtureController(diagnostics, "native-controller", () =>
            command(
              process.execPath,
              [
                "--import",
                loader,
                "--test",
                ...files.map((file) => join(home, "tests/native", file)),
              ],
              {
                signal,
                timeout: 900000,
                executionDeadline: began + 900000,
                cleanupTimeout: 5000,
                log: capture.path,
                env,
              },
            ),
          );
        },
        (deadline) => {
          stopDeadline = deadline;
          return owner.writeReport(evidence);
        },
        browserFixtureClock,
        AbortSignal.any([root.signal, active.signal]),
      );
      for (const id of ["startup-cancel", "stalled-close", "profile-timeout"]) {
        const row = owner.snapshot().cases.find((c) => c.id === id);
        if (
          !row ||
          row.held ||
          row.emergency ||
          !row.receipts.some(
            (r) => r.origin === "profile" && r.fulfilled && r.closeObserved,
          )
        )
          throw new Error(
            `Missing profile-origin browser completion for ${id}`,
          );
      }
    }
    if (owner.snapshot().errors.length)
      throw new Error("Browser fixture control failed");
    workerCompleted = true;
  } catch (error) {
    errors.push(error);
  } finally {
    closing = true;
    stopDeadline ??= performance.now() + 10000;
    try {
      await owner.stop(stopDeadline);
    } catch (error) {
      errors.push(error);
    }
    if (owner.snapshot().cases.some((c) => c.held)) {
      await admit(
        browserFixtureClock,
        () => owner.writeReport(evidence),
        stopDeadline,
        "report",
      ).catch((error: unknown) => errors.push(error));
      process.stderr.write(
        fixtureDiagnostic({
          phase: "fixture-terminal",
          category: "owner-unknown",
          status: null,
        }),
      );
      // Keep the real pending acquisition/handle reachable until the enclosing
      // owned command stops this launcher. No numeric browser fallback exists.
      await new Promise<void>(() => {});
    }
    try {
      for (const socket of sockets) socket.destroy();
      await bound(
        browserFixtureClock,
        new Promise<void>((resolve, reject) =>
          server.close((error) => (error ? reject(error) : resolve())),
        ),
        Math.min(stopDeadline, performance.now() + 1000),
        "listener",
      );
      ipcCompleted = true;
    } catch (error) {
      errors.push(error);
    }
    try {
      await admit(
        browserFixtureClock,
        () => owner.writeReport(evidence),
        stopDeadline,
        "report",
      );
      for (const [slot, capture] of captures) {
        try {
          const metadata = await capture.check(stopDeadline);
          diagnostics.note({
            phase: slot === "probe" ? "probe-controller" : "native-controller",
            category: "capture-checked",
            slot,
            ...metadata,
            status: null,
          });
        } catch (error) {
          errors.push(error);
          diagnostics.note({
            phase: slot === "probe" ? "probe-controller" : "native-controller",
            category: "capture-invalid",
            slot,
            status: null,
          });
        }
      }
      await diagnostics.write(protectedFolder, stopDeadline);
      await admit(
        browserFixtureClock,
        () =>
          writeFile(
            evidence + ".runtime.json",
            JSON.stringify({
              workerCompleted,
              ipcCompleted,
              source: "fixture-library-owner",
            }) + "\n",
          ),
        stopDeadline,
        "report",
      );
    } catch (error) {
      errors.push(error);
    }
    process.off("SIGTERM", term);
    process.off("SIGINT", int);
    if (ipcCompleted) {
      try {
        await admit(
          browserFixtureClock,
          () => rm(folder, { recursive: true, force: true }),
          stopDeadline,
          "fixture-directory",
        );
      } catch (error) {
        errors.push(error);
      }
    }
  }
  if (errors.length === 1) throw errors[0];
  if (errors.length) throw new AggregateError(errors, "Browser fixture failed");
  process.stdout.write(
    fixtureDiagnostic({
      phase: "fixture-terminal",
      category: "passed",
      status: 0,
    }),
  );
}

if (
  process.argv[1] &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  await runFixture(process.argv[2] ?? "").catch(() => {
    process.stderr.write(
      fixtureDiagnostic({
        phase: "fixture-terminal",
        category: "failed",
        status: null,
      }),
    );
    process.exitCode = 1;
  });
}
