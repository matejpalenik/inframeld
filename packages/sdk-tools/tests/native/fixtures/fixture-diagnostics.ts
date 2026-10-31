/** Passive protected capture and fixed diagnostic I/O. Callers own lifecycle deadlines. */
import { chmod, mkdtemp, open, rm, writeFile } from "node:fs/promises";
import { constants } from "node:fs";
import { basename, join } from "node:path";
import { withResources } from "../../../src/system/process.ts";
import { describeError } from "../../../src/workflows/stages.ts";

export type FixtureDiagnosticScope = "broker" | "assertion" | "worker";
export type FixtureCaptureSlot = "probe" | "controller" | "timeout";
export interface FixtureCaptureMetadata {
  bytes: number;
  device: number;
  inode: number;
}
export interface FixtureCapture {
  path: string;
  check(): Promise<FixtureCaptureMetadata>;
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
    "failure",
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
  if ("failure" in row) record.failure = JSON.parse(describeError(row.failure));
  return JSON.stringify(record) + "\n";
}

export class FixtureDiagnostics {
  private readonly records: string[] = [];
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
    writer: (path: string, bytes: string) => Promise<void> = async (
      path,
      bytes,
    ) => {
      await writeFile(path, bytes, { mode: 0o600 });
    },
  ): Promise<void> {
    await writer(join(folder, this.scope + "-status.json"), this.snapshot());
  }
}

export async function prepareFixtureCapture(
  folder: string,
  slot: FixtureCaptureSlot,
): Promise<FixtureCapture> {
  if (!["probe", "controller", "timeout"].includes(slot))
    throw new Error("Invalid protected capture");
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
    check() {
      return (checking ??= (async () => {
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
      })());
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
      ...(failed ? { failure } : {}),
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

/** Keep raw captures outside the ordinary browser-owner artifact directory. */
export async function acquireProtectedFixtureDirectory(
  report: string,
): Promise<string> {
  const folder = await mkdtemp(join("/tmp", basename(report) + ".protected-"));
  try {
    await chmod(folder, 0o700);
  } catch (error) {
    await rm(folder, { recursive: true, force: true });
    throw error;
  }
  return folder;
}
