import { parse, stringify } from "smol-toml";
import assert from "node:assert/strict";

/** Only the generated dependency table is owned by regeneration. */
export function updateCargoDependencies(
  current: string,
  generated: string,
): string {
  const manifest = parse(current);
  const required = parse(generated);
  assert.ok(required.dependencies, "Generator did not emit dependencies");
  if (
    JSON.stringify(manifest.dependencies) ===
    JSON.stringify(required.dependencies)
  )
    return current;
  manifest.dependencies = required.dependencies;
  return stringify(manifest);
}
