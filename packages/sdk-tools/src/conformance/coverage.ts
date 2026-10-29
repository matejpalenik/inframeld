import { z } from "zod";
export interface CaseMetadata {
  id: string;
  operation: string;
  outcome: "success" | "failure";
}
const schemaShape = z.object({
  paths: z.record(z.string(), z.record(z.string(), z.unknown())),
});
export interface OperationMetadata {
  method: string;
  path: string;
  encodedPathParams?: string[];
}

export function assertCoverage(
  input: unknown,
  cases: readonly CaseMetadata[],
  bindings: Record<string, readonly string[]>,
): Map<string, OperationMetadata> {
  const schema = schemaShape.parse(input);
  const operations = new Map<string, OperationMetadata>();
  for (const [path, item] of Object.entries(schema.paths)) {
    for (const [method, operation] of Object.entries(item)) {
      if (
        ![
          "get",
          "post",
          "put",
          "patch",
          "delete",
          "head",
          "options",
          "trace",
        ].includes(method)
      )
        continue;
      const id = z
        .object({ operationId: z.string().optional() })
        .parse(operation).operationId;
      if (!id || operations.has(id))
        throw new Error(`Missing or duplicate operationId: ${id}`);
      const { parameters } = z
        .object({
          parameters: z
            .array(
              z.object({
                name: z.string().optional(),
                in: z.string().optional(),
                schema: z
                  .object({
                    "x-inframeld-encoded-path": z.boolean().optional(),
                  })
                  .passthrough()
                  .optional(),
              }),
            )
            .optional(),
        })
        .parse(operation);
      const encodedPathParams =
        parameters?.flatMap((p) =>
          p.name && p.in === "path" && p.schema?.["x-inframeld-encoded-path"]
            ? [p.name]
            : [],
        ) ?? [];
      operations.set(id, {
        method: method.toUpperCase(),
        path,
        ...(encodedPathParams.length ? { encodedPathParams } : {}),
      });
    }
  }
  if (new Set(cases.map((entry) => entry.id)).size !== cases.length)
    throw new Error("Duplicate scenario");
  for (const entry of cases) {
    if (!operations.has(entry.operation))
      throw new Error(`Unknown scenario operation ${entry.operation}`);
  }
  for (const id of operations.keys()) {
    if (
      !cases.some(
        (entry) => entry.operation === id && entry.outcome === "success",
      )
    )
      throw new Error(`Missing success scenario for ${id}`);
    for (const [profile, available] of Object.entries(bindings)) {
      if (!available.includes(id))
        throw new Error(`Missing ${profile} binding for ${id}`);
    }
  }
  return operations;
}
