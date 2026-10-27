import { prepare, emit, targets } from "../generation/generators.ts";
import assert from "node:assert/strict";
import { readFile, writeFile, cp, rm, mkdtemp } from "node:fs/promises";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { home, cache, type Language } from "../config.ts";
import { run } from "../system/run.ts";
import { withResources } from "../system/process.ts";
import { assertNoDrift } from "../generation/drift.ts";
import { updateCargoDependencies } from "../generation/cargo.ts";
import type { GenerationTarget } from "../generation/types.ts";
export async function generate(
  language: Language,
  check = false,
): Promise<void> {
  const tool = await prepare(language);
  const work = await mkdtemp(join(tmpdir(), "inframeld-sdk-generate-"));
  await withResources(
    async () => {
      const exported = join(work, "openapi.json");
      await run(
        "uv",
        [
          "run",
          "--directory",
          "apps/backend",
          "python",
          "-m",
          "tests.support.sdk_server",
          "export",
          exported,
        ],
        "fixture-export",
        { env: { UV_CACHE_DIR: join(cache, "uv") } },
      );
      if (check)
        assert.equal(
          await readFile(join(home, "fixtures/openapi.json"), "utf8"),
          await readFile(exported, "utf8"),
          "Native fixture OpenAPI drifted",
        );
      const outputs: {
        target: GenerationTarget;
        dest: string;
        cargo?: string;
      }[] = [];
      for (const target of targets(language)) {
        const dest = join(work, target.kind, "generated");
        await emit(
          language,
          target.kind === "fixtures" ? { ...target, schema: exported } : target,
          tool,
          dest,
        );
        let cargo: string | undefined;
        if (language === "rust") {
          const current = await readFile(
            join(target.directory, "Cargo.toml"),
            "utf8",
          );
          const deps = await readFile(join(dest, "REQUIRED_DEPS.toml"), "utf8");
          cargo = updateCargoDependencies(current, deps);
          if (check)
            assert.equal(
              current,
              cargo,
              `${target.kind} Cargo dependencies drifted`,
            );
        }
        if (check)
          await assertNoDrift(join(target.directory, "generated"), dest);
        outputs.push({ target, dest, cargo });
      }
      if (!check) await cp(exported, join(home, "fixtures/openapi.json"));
      if (!check)
        for (const { target, dest, cargo } of outputs) {
          await rm(join(target.directory, "generated"), {
            recursive: true,
            force: true,
          });
          await cp(dest, join(target.directory, "generated"), {
            recursive: true,
          });
          if (cargo)
            await writeFile(join(target.directory, "Cargo.toml"), cargo);
        }
    },
    () => rm(work, { recursive: true, force: true }),
  );
}
