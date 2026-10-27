export interface Stage {
  name: string;
  status: "passed" | "failed";
  milliseconds: number;
  error?: string;
  detail?: unknown;
}
export function describeError(error: unknown): string {
  if (error instanceof AggregateError)
    return `${error.stack}\n${error.errors.map(describeError).join("\n")}`;
  return error instanceof Error
    ? (error.stack ?? String(error))
    : String(error);
}
export async function stage(
  stages: Stage[],
  name: string,
  task: () => Promise<unknown>,
): Promise<void> {
  const start = performance.now();
  try {
    const detail = await task();
    stages.push({
      name,
      status: "passed",
      milliseconds: performance.now() - start,
      detail,
    });
    console.log(`PASS ${name}`);
  } catch (error) {
    const message = describeError(error);
    stages.push({
      name,
      status: "failed",
      milliseconds: performance.now() - start,
      error: message,
    });
    console.error(`FAIL ${name}\n${message}`);
  }
}
