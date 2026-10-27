import assert from "node:assert/strict";
import test from "node:test";
import { budgets, profileBudget } from "../../src/system/budgets.ts";

test("profile overrides are bounded positive integer development budgets", () => {
  assert.equal(profileBudget("300000"), budgets.profile);
  assert.equal(profileBudget("600000"), 600000);
  for (const value of ["0", "-1", "NaN", "2000", "30000.5", "3600001"])
    assert.throws(() => profileBudget(value), /SDK_PROFILE_TIMEOUT_MS/);
});
