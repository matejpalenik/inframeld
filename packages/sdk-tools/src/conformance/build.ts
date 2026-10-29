import { join } from "node:path";
import { build } from "esbuild";
import { z } from "zod";
import { root, home, cache, packageRoot, type Language } from "../config.ts";
import { run } from "../system/run.ts";
import { buildTypescript } from "../system/typescript.ts";
import { wheel, python, pythonVersions } from "../system/python.ts";

export const runtimeSchema = z.object({
  bindings: z.array(z.string()),
  rustExecutable: z.string().optional(),
  pythonExecutable: z.string().optional(),
  typescriptBundle: z.string().optional(),
});
export type Runtime = z.infer<typeof runtimeSchema>;

export async function buildRuntime(
  language: Language,
  work: string,
): Promise<Runtime> {
  if (language === "rust") {
    await run(
      "cargo",
      ["build", "--locked", "-p", "inframeld-sdk-conformance-driver"],
      "rust-compilation",
    );
    const rustExecutable = join(
      process.env.CARGO_TARGET_DIR || join(root, "target"),
      "debug/inframeld-sdk-conformance-driver",
    );
    const bindings = z
      .array(z.string())
      .parse(
        JSON.parse(
          (await run(rustExecutable, ["--bindings"], "rust-bindings")).stdout,
        ),
      );
    return { bindings, rustExecutable };
  }
  if (language === "python") {
    const production = await wheel(
      packageRoot("python"),
      join(work, "production-wheel"),
      "python-wheel",
    );
    const fixtures = await wheel(
      join(home, "fixtures/python"),
      join(work, "fixture-wheel"),
      "python-fixture-wheel",
    );
    const environment = join(work, "python-runtime");
    const versions = await pythonVersions();
    await run(
      "uv",
      ["venv", environment, "--python", versions.primary],
      "python-runtime-env",
    );
    const pythonExecutable = join(environment, "bin/python");
    await run(
      "uv",
      [
        "pip",
        "install",
        "--python",
        pythonExecutable,
        "--constraint",
        join(home, "requirements.lock"),
        production,
        fixtures,
      ],
      "python-runtime-install",
    );
    const bindings = z
      .array(z.string())
      .parse(
        JSON.parse(
          (
            await run(
              pythonExecutable,
              [join(home, "drivers/python/main.py"), "--bindings"],
              "python-bindings",
            )
          ).stdout,
        ),
      );
    return { bindings, pythonExecutable };
  }
  await buildTypescript("typescript-compilation");
  const typescriptBundle = join(work, "typescript-driver.mjs");
  await build({
    entryPoints: [join(home, "drivers/typescript.ts")],
    bundle: true,
    platform: "neutral",
    format: "esm",
    outfile: typescriptBundle,
  });
  const driver: import("./protocol.ts").NativeDriver = await import(
    new URL(`file://${typescriptBundle}`).href
  );
  return { bindings: [...driver.bindings], typescriptBundle };
}

export async function checkNativeModels(
  language: Language,
  runtime: Runtime,
): Promise<void> {
  if (language === "rust") {
    await run(
      "cargo",
      [
        "test",
        "--locked",
        "-p",
        "inframeld-sdk-conformance-driver",
        "models::",
      ],
      "rust-models",
    );
    return;
  }
  if (language === "python") {
    if (!runtime.pythonExecutable) throw new Error("Missing Python runtime");
    await run(
      runtime.pythonExecutable,
      [join(home, "drivers/python/models_test.py")],
      "python-model-contract",
    );
    return;
  }
  await run(
    process.execPath,
    [
      "--import",
      join(home, "node_modules/tsx/dist/loader.mjs"),
      "--test",
      join(home, "tests/native/response-integrity.test.ts"),
      join(home, "tests/native/typed-failures.test.ts"),
      join(home, "tests/native/default-transport.test.ts"),
    ],
    "typescript-native-regressions",
  );
}

export async function checkNativeRegressions(
  language: Language,
  runtime: Runtime,
): Promise<void> {
  if (language === "rust") {
    await run(
      "cargo",
      [
        "test",
        "--locked",
        "-p",
        "inframeld-sdk-conformance-driver",
        "lifecycle::",
      ],
      "rust-driver-lifecycle",
    );
  } else if (language === "python") {
    if (!runtime.pythonExecutable) throw new Error("Missing Python runtime");
    await run(
      runtime.pythonExecutable,
      [
        "-m",
        "unittest",
        "protocol_test",
        "observations_test",
        "lifecycle_test",
      ],
      "python-driver-regressions",
      { cwd: join(home, "drivers/python") },
    );
  } else {
    await run(
      process.execPath,
      [
        "--import",
        join(home, "node_modules/tsx/dist/loader.mjs"),
        "--test",
        join(home, "tests/native/driver.test.ts"),
        join(home, "tests/native/lifecycle.test.ts"),
        join(home, "tests/native/profile-resources.test.ts"),
      ],
      "typescript-driver-regressions",
    );
  }
}

export async function typecheckNative(language: Language): Promise<void> {
  if (language === "python") {
    await run(
      python,
      [
        "-m",
        "pyright",
        "-p",
        join(home, "pyrightconfig.json"),
        "--venvpath",
        cache,
      ],
      "python-driver-types",
    );
    await run(
      python,
      [
        "-m",
        "ruff",
        "check",
        "--config",
        join(home, "pyproject.toml"),
        join(home, "drivers/python"),
        join(home, "consumers/python"),
      ],
      "python-driver-lint",
    );
    await run(
      python,
      [
        "-m",
        "ruff",
        "format",
        "--check",
        "--config",
        join(home, "pyproject.toml"),
        join(home, "drivers/python"),
        join(home, "consumers/python"),
      ],
      "python-driver-format",
    );
  } else if (language === "rust") {
    await run(
      "cargo",
      [
        "check",
        "--locked",
        "--manifest-path",
        join(home, "consumers/rust/Cargo.toml"),
      ],
      "rust-consumer-types",
    );
  } else {
    await run(
      join(home, "node_modules/.bin/tsc"),
      ["-p", join(home, "tsconfig.native.json")],
      "typescript-native-types",
    );
  }
}
