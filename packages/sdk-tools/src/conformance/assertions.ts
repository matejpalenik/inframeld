import assert from "node:assert/strict";
import type { JsonValue, Observation } from "./protocol.ts";

export function assertDispatch(
  witness: Record<string, JsonValue>,
  method: string,
  path: string,
): void {
  assert.equal(witness.method, method, "Wrong dispatched HTTP method");
  assert.equal(witness.path, path, "Wrong dispatched HTTP path");
  assert.equal(witness.count, 1, "A native call must dispatch exactly once");
}

export function assertSuccess(
  observation: Observation,
  status: number,
): Record<string, JsonValue> {
  assert.equal(observation.kind, "success", JSON.stringify(observation));
  assert.equal(observation.status, status, "Unexpected native HTTP status");
  assert.ok(
    ["generated-model", "generated-schema"].includes(observation.validation),
    "Missing native validated result",
  );
  assert.ok(
    observation.body &&
      typeof observation.body === "object" &&
      !Array.isArray(observation.body),
    "Expected a JSON object result",
  );
  return observation.body;
}
export function assertJsonBody(
  witness: Record<string, JsonValue>,
  expected: Record<string, JsonValue>,
): void {
  assert.deepEqual(
    witness.jsonBody,
    expected,
    "Backend received a different JSON body",
  );
}
export function headerValues(observation: Observation, name: string): string[] {
  return observation.headers
    .filter(
      (header) =>
        header.name.toLowerCase() === name.toLowerCase() &&
        header.encoding === "utf8",
    )
    .map((header) => header.value);
}
