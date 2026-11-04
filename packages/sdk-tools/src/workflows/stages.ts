import { ProcessFailure, hasConfirmedCleanup } from "../system/process.ts";

export interface Stage {
  name: string;
  status: "passed" | "failed";
  milliseconds: number;
  error?: string;
  detail?: unknown;
}
export interface StageResult {
  passed: boolean;
  mayStartProcess: boolean;
}

/** Fixed classifications only. Original errors remain available to their owner. */
export function describeError(error: unknown): string {
  const deniedChecks = [
    "SDK_DENIED_COMMAND_EXIT",
    "SDK_DENIED_RECEIPT",
    "SDK_DENIED_ORIGINAL_ERRORS",
    "SDK_DENIED_CLOCK_BUDGET",
    "SDK_DENIED_PS_OBSERVATION",
    "SDK_DENIED_TARGET_LIVE",
    "SDK_DENIED_INDEPENDENT_RECOVERY",
  ];
  const seen = new Set<object>();
  let remaining = 16;
  const arrayValues = (value: unknown, maximum: number): unknown[] => {
    if (!Array.isArray(value)) return [];
    const length: unknown = Object.getOwnPropertyDescriptor(
      value,
      "length",
    )?.value;
    if (
      typeof length !== "number" ||
      !Number.isSafeInteger(length) ||
      length < 0
    )
      return [];
    const result: unknown[] = [];
    for (let index = 0; index < Math.min(length, maximum); index++)
      result.push(Object.getOwnPropertyDescriptor(value, String(index))?.value);
    return result;
  };
  const visit = (
    value: unknown,
    depth: number,
    nodeFailure = false,
  ): object => {
    if (depth > 4 || --remaining < 0) return { kind: "truncated" };
    try {
      if (!value || typeof value !== "object") return { kind: "unknown" };
      const fields = Object.getOwnPropertyDescriptors(value);
      const message = fields.message;
      const fixedMessage =
        nodeFailure &&
        !Object.hasOwn(fields, "code") &&
        message &&
        "value" in message &&
        typeof message.value === "string" &&
        deniedChecks.includes(message.value)
          ? message.value
          : undefined;
      const code: unknown = fixedMessage ?? fields.code?.value;
      const wrappedByNode =
        code === "ERR_TEST_FAILURE" &&
        fields.failureType?.value === "testCodeFailure";
      const deniedCheck =
        typeof code === "string" && deniedChecks.includes(code);
      const aggregate =
        value instanceof AggregateError ||
        (nodeFailure && Array.isArray(fields.errors?.value));
      if (
        !(value instanceof Error) &&
        !wrappedByNode &&
        !deniedCheck &&
        !aggregate
      )
        return { kind: "unknown" };
      if (seen.has(value)) return { kind: "cycle" };
      seen.add(value);
      const detail: Record<string, unknown> = {
        kind: aggregate ? "aggregate" : "error",
      };
      detail.code =
        typeof code === "string" &&
        (deniedCheck ||
          [
            "EPIPE",
            "ECONNRESET",
            "ECONNABORTED",
            "EIO",
            "EBADF",
            "ETIMEDOUT",
            "ERR_STREAM_DESTROYED",
            "ERR_STREAM_WRITE_AFTER_END",
            "ERR_SOCKET_CLOSED",
          ].includes(code))
          ? code
          : "unknown";
      const syscall: unknown = fields.syscall?.value;
      detail.syscall =
        syscall === "read" || syscall === "write" ? syscall : "unknown";
      if (value instanceof ProcessFailure) {
        detail.kind = hasConfirmedCleanup(value)
          ? "command-failed"
          : "cleanup-unconfirmed";
        const state: unknown = fields.state?.value;
        if (state && typeof state === "object") {
          const facts = Object.getOwnPropertyDescriptors(state);
          detail.helperClosed = facts.helperClosed?.value === true;
          detail.streamsEnded = facts.streamsEnded?.value === true;
          const code: unknown = facts.helperCode?.value;
          detail.helperCode = Number.isSafeInteger(code) ? code : null;
          const terminal: unknown = facts.terminal?.value;
          if (terminal && typeof terminal === "object") {
            const row = Object.getOwnPropertyDescriptors(terminal);
            detail.leaderReaped = row.leaderReaped?.value === true;
            detail.groupState = ["quiescent", "live", "unknown"].includes(
              row.groupState?.value,
            )
              ? row.groupState?.value
              : "unknown";
            const allowed = [
              "group-observation-failed",
              "group-shutdown-unconfirmed",
              "target-reap-unconfirmed",
              "group-signal-failed",
              "wait-ownership-lost",
              "observation-child-unresolved",
            ];
            const errors: unknown = row.errors?.value;
            if (Array.isArray(errors))
              detail.errors = arrayValues(errors, 16).map((entry: unknown) =>
                typeof entry === "string" &&
                (allowed.includes(entry) ||
                  /^ps-(initial|term|kill)-(spawn|read|wait|parse|reap)-(timeout|os|nonzero|malformed)$/.test(
                    entry,
                  ))
                  ? entry
                  : "unknown",
              );
          }
        }
      }
      const nested: unknown = fields.errors?.value;
      if (aggregate && Array.isArray(nested))
        detail.errors = arrayValues(nested, 4).map((entry: unknown) =>
          visit(entry, depth + 1, nodeFailure || wrappedByNode),
        );
      if ("value" in (fields.cause ?? {}))
        detail.cause = visit(
          fields.cause!.value,
          depth + 1,
          nodeFailure || wrappedByNode,
        );
      return detail;
    } catch {
      return { kind: "unknown" };
    }
  };
  const output = JSON.stringify(visit(error, 0));
  return Buffer.byteLength(output) <= 4096 ? output : '{"kind":"truncated"}';
}

export async function stage(
  stages: Stage[],
  name: string,
  task: () => Promise<unknown>,
  admitted = true,
): Promise<StageResult> {
  const start = performance.now();
  if (!admitted) {
    stages.push({
      name,
      status: "failed",
      milliseconds: 0,
      error: "Blocked by failed prerequisite",
      detail: { blocked: true },
    });
    return { passed: false, mayStartProcess: true };
  }
  try {
    const detail = await task();
    stages.push({
      name,
      status: "passed",
      milliseconds: performance.now() - start,
      detail,
    });
    console.log(`PASS ${name}`);
    return { passed: true, mayStartProcess: true };
  } catch (error) {
    const message = describeError(error);
    stages.push({
      name,
      status: "failed",
      milliseconds: performance.now() - start,
      error: message,
    });
    console.error(`FAIL ${name}\n${message}`);
    // Only explicit owner evidence permits another subprocess after failure.
    return { passed: false, mayStartProcess: hasConfirmedCleanup(error) };
  }
}
