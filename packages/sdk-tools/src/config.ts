import { fileURLToPath } from "node:url";
import { dirname, resolve, join } from "node:path";

export const home = resolve(dirname(fileURLToPath(import.meta.url)), "..");
export const root = resolve(home, "../..");
export const artifacts = join(home, "artifacts");
export const cache =
  process.env.INFRAMELD_SDK_TOOLS_DIR ||
  join(root, "node_modules/.cache/inframeld-sdk-tools");
export const languages = ["rust", "typescript", "python"] as const;
export type Language = (typeof languages)[number];
export const profiles = {
  rust: ["rust"],
  typescript: ["typescript-node", "typescript-chromium"],
  python: ["python-sync", "python-async"],
} as const;
export type Profile = (typeof profiles)[Language][number];
export const packageRoot = (language: Language): string =>
  join(root, "packages/sdk-" + language);
