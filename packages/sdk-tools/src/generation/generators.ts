import { join } from "node:path";
import { home, root, packageRoot, type Language } from "../config.ts";
import { prepareRust, emitRust } from "./rust.ts";
import { prepareTypescript, emitTypescript } from "./typescript.ts";
import { preparePython, emitPython } from "./python.ts";
import type { GenerationTarget, Generator } from "./types.ts";
export const generators: Record<Language, Generator> = {
  rust: { prepare: prepareRust, emit: emitRust },
  typescript: { prepare: prepareTypescript, emit: emitTypescript },
  python: { prepare: preparePython, emit: emitPython },
};
export const prepare = (language: Language, test = false): Promise<string> =>
  generators[language].prepare(test);
export const emit = (
  language: Language,
  target: GenerationTarget,
  tool: string,
  destination: string,
): Promise<void> => generators[language].emit(target, tool, destination);
export const targets = (language: Language): GenerationTarget[] => [
  {
    kind: "production",
    directory: packageRoot(language),
    schema: join(root, "contracts/openapi/v1/inframeld-v1.json"),
  },
  {
    kind: "fixtures",
    directory: join(home, "fixtures", language),
    schema: join(home, "fixtures/openapi.json"),
  },
  ...(language === "rust"
    ? [
        {
          kind: "capabilities" as const,
          directory: join(home, "fixtures/rust-capabilities"),
          schema: join(home, "fixtures/patch-capabilities.json"),
        },
      ]
    : []),
];
