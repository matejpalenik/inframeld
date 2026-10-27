/** Resource ownership budgets. Profile overrides are local development controls. */
export const budgets = {
  case: 30_000,
  startup: 30_000,
  profile: 300_000,
  cleanup: 20_000,
  control: 2000,
  resourceCleanup: 5000,
} as const;

export function profileBudget(
  value = process.env.SDK_PROFILE_TIMEOUT_MS,
): number {
  if (value === undefined) return budgets.profile;
  const milliseconds = Number(value);
  if (
    !Number.isSafeInteger(milliseconds) ||
    milliseconds < budgets.case ||
    milliseconds > 3_600_000
  )
    throw new Error(
      "SDK_PROFILE_TIMEOUT_MS must be an integer between 30000 and 3600000",
    );
  return milliseconds;
}
