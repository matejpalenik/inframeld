import assert from "node:assert/strict";
import test from "node:test";
import { parse } from "smol-toml";
import { updateCargoDependencies } from "../../src/generation/cargo.ts";

test("regeneration preserves features and target dependencies outside its owned table", () => {
  const current =
    '[package]\nname="consumer"\nversion="0.0.0"\n[dependencies]\nold="1"\n[features]\nextra=[]\n[target.\'cfg(unix)\'.dependencies]\nlibc="0.2"\n[dev-dependencies]\ntest="1"\n';
  const generated = '[dependencies]\nnew="2"\n[features]\ngenerator_only=[]\n';
  const updated = parse(updateCargoDependencies(current, generated));
  const original = parse(current);
  assert.deepEqual(
    JSON.parse(JSON.stringify(updated)),
    JSON.parse(JSON.stringify({ ...original, dependencies: { new: "2" } })),
  );
});

test("an already current Cargo manifest remains byte-identical", () => {
  const current = '# retain human comments\n[dependencies]\nx="1"\n';
  assert.equal(
    updateCargoDependencies(current, '[dependencies]\nx="1"'),
    current,
  );
});
