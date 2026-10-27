import { snapshot } from "../system/files.ts";

export async function assertNoDrift(
  expected: string,
  actual: string,
): Promise<void> {
  const sourceFiles = async (directory: string) =>
    Object.fromEntries(
      Object.entries(await snapshot(directory)).filter(
        ([key]) => !key.split("/").includes("__pycache__"),
      ),
    );
  const left = await sourceFiles(expected);
  const right = await sourceFiles(actual);
  const differences = [
    ...new Set([...Object.keys(left), ...Object.keys(right)]),
  ].filter((key) => left[key] !== right[key]);
  if (differences.length)
    throw new Error(`Regeneration differs: ${differences.join(", ")}`);
}
