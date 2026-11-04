import assert from "node:assert/strict"
import { spawn } from "node:child_process"
import {
  access,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises"
import { tmpdir } from "node:os"
import { dirname, join, resolve } from "node:path"
import { test } from "node:test"

const helper = resolve("tests/fixtures/prepare_build_context.py")
async function exists(path: string) {
  try {
    await access(path)
    return true
  } catch {
    return false
  }
}
async function file(path: string, content: string) {
  await mkdir(dirname(path), { recursive: true })
  await writeFile(path, content)
}
async function run(
  source: string,
  destination: string,
  recipientProof = false
) {
  const child = spawn(
    "python3",
    [
      helper,
      source,
      destination,
      ...(recipientProof ? ["--recipient-proof"] : []),
    ],
    {
      stdio: ["ignore", "pipe", "pipe"],
    }
  )
  let output = ""
  child.stdout.on("data", (value: Buffer) => {
    output += value.toString()
  })
  child.stderr.on("data", (value: Buffer) => {
    output += value.toString()
  })
  const code = await new Promise<number | null>((resolveResult, reject) => {
    const timer = setTimeout(() => {
      child.kill("SIGKILL")
      reject(new Error("Context preparation exceeded the private test bound."))
    }, 3_000)
    child.once("error", reject)
    child.once("close", (code) => {
      clearTimeout(timer)
      resolveResult(code)
    })
  })
  return { code, output }
}

test("recipient-proof context copies current locked Rust sources while excluding host artifacts and secrets", async () => {
  await scenario(async (source, destination) => {
    for (const name of ["Cargo.toml", "Cargo.lock", "rust-toolchain.toml"])
      await file(join(source, name), `public-${name}\n`)
    for (const tree of [
      "apps/cli",
      "packages/sdk-rust",
      "packages/sdk-tools/drivers/rust",
      "packages/sdk-tools/fixtures/rust",
      "packages/sdk-tools/fixtures/rust-capabilities",
    ]) {
      await file(join(source, tree, "Cargo.toml"), "public-crate\n")
      await file(join(source, tree, "src/lib.rs"), "// current source\n")
      await file(join(source, tree, ".env"), "private-context-test-secret")
      await file(
        join(source, tree, "target/debug/old-artifact"),
        "old executable"
      )
    }
    await file(
      join(source, "apps/web/tests/fixtures/recipient-proof.Dockerfile"),
      "FROM public-proof-build\n"
    )
    assert.equal((await run(source, destination, true)).code, 0)
    assert.equal(await exists(join(destination, "Cargo.lock")), true)
    assert.equal(await exists(join(destination, "apps/cli/src/lib.rs")), true)
    assert.equal(
      await exists(join(destination, "packages/sdk-rust/src/lib.rs")),
      true
    )
    assert.equal(await exists(join(destination, "apps/cli/.env")), false)
    assert.equal(await exists(join(destination, "apps/cli/target")), false)
    assert.equal(
      await exists(join(destination, "apps/web/lib/public.ts")),
      false
    )
    assert.equal(
      await exists(join(destination, "packages/sdk-typescript")),
      false
    )
    assert.equal(
      await readFile(
        join(destination, "apps/web/tests/fixtures/recipient-proof.Dockerfile"),
        "utf8"
      ),
      "FROM public-proof-build\n"
    )
  })
})
async function scenario(
  check: (source: string, destination: string, outside: string) => Promise<void>
) {
  const parent = await mkdtemp(join(tmpdir(), "account-context-test-"))
  const source = join(parent, "source")
  const destination = join(parent, "context")
  const outside = join(parent, "outside")
  try {
    await file(join(source, "package.json"), '{"private":true}')
    await file(join(source, "pnpm-lock.yaml"), "lockfileVersion: '9.0'\n")
    await file(
      join(source, "pnpm-workspace.yaml"),
      "packages: ['apps/*', 'packages/*']\n"
    )
    await file(
      join(source, ".npmrc"),
      "min-release-age=3\nengine-strict=true\n"
    )
    await file(
      join(source, "apps/web/lib/public.ts"),
      "export const publicSource = true\n"
    )
    await file(
      join(source, "apps/web/tests/fixtures/.dockerignore"),
      "**/.env*\n**/node_modules\n"
    )
    await file(
      join(source, "packages/sdk-typescript/generated/public.ts"),
      "export const generatedSource = true\n"
    )
    await file(join(outside, "secret.txt"), "private-context-test-secret")
    await check(source, destination, outside)
  } finally {
    await rm(parent, { recursive: true, force: true })
  }
}

test("a public web/SDK source context preserves pnpm policy bytes and ordinary root ignore", async () => {
  await scenario(async (source, destination) => {
    assert.equal((await run(source, destination)).code, 0)
    assert.equal(await exists(destination), true)
    assert.equal(
      await readFile(join(destination, "apps/web/lib/public.ts"), "utf8"),
      "export const publicSource = true\n"
    )
    assert.equal(
      await readFile(
        join(destination, "packages/sdk-typescript/generated/public.ts"),
        "utf8"
      ),
      "export const generatedSource = true\n"
    )
    assert.equal(
      await readFile(join(destination, ".npmrc"), "utf8"),
      await readFile(join(source, ".npmrc"), "utf8")
    )
    assert.equal(
      await readFile(join(destination, ".dockerignore"), "utf8"),
      await readFile(
        join(source, "apps/web/tests/fixtures/.dockerignore"),
        "utf8"
      )
    )
    assert.equal((await lstat(destination)).mode & 0o777, 0o700)
    assert.equal(
      (await lstat(join(destination, "apps/web/lib"))).mode & 0o777,
      0o755
    )
  })
})

test("credential, dependency and cache material is excluded before following any input", async () => {
  await scenario(async (source, destination, outside) => {
    for (const name of [
      ".env.local",
      "nested/service.env",
      ".npmrc",
      "identity.key",
      "server.pem",
      "nested/.cache/raw.log",
      ".next/cache/data",
      "node_modules/dependency/code.js",
      "dist/result.js",
      "test-results/storage.json",
    ])
      await file(join(source, "apps/web", name), "private-context-test-secret")
    await symlink(join(outside, "secret.txt"), join(source, "apps/web/.env"))
    await symlink(outside, join(source, "packages/sdk-typescript/node_modules"))
    assert.equal((await run(source, destination)).code, 0)
    assert.equal(
      await exists(join(destination, "apps/web/lib/public.ts")),
      true
    )
    for (const name of [
      ".env",
      ".env.local",
      "nested/service.env",
      ".npmrc",
      "identity.key",
      "server.pem",
      "nested/.cache",
      ".next",
      "node_modules",
      "dist",
      "test-results",
    ])
      assert.equal(await exists(join(destination, "apps/web", name)), false)
    assert.equal(
      await exists(join(destination, "packages/sdk-typescript/node_modules")),
      false
    )
    assert.equal(
      await readFile(join(outside, "secret.txt"), "utf8"),
      "private-context-test-secret"
    )
  })
})

for (const directoryLink of [false, true]) {
  test(`a remaining ${directoryLink ? "directory" : "file"} symlink is rejected without retaining a partial context`, async () => {
    await scenario(async (source, destination, outside) => {
      await symlink(
        directoryLink ? outside : join(outside, "secret.txt"),
        join(source, "apps/web/lib/linked")
      )
      const result = await run(source, destination)
      assert.equal(result.code, 1)
      assert.equal(await exists(destination), false)
      assert.doesNotMatch(result.output, /private-context-test-secret/)
      assert.equal(
        await readFile(join(outside, "secret.txt"), "utf8"),
        "private-context-test-secret"
      )
    })
  })
}

test("a symlink in an allocated source ancestor cannot redirect the copy outside its tree", async () => {
  await scenario(async (source, destination, outside) => {
    await mkdir(join(outside, "web"))
    await rm(join(source, "apps"), { recursive: true })
    await symlink(outside, join(source, "apps"))
    assert.equal((await run(source, destination)).code, 1)
    assert.equal(await exists(destination), false)
  })
})

test("preexisting destination data is preserved instead of being cleaned as owned context", async () => {
  await scenario(async (source, destination) => {
    await file(join(destination, "foreign.txt"), "preserve-existing-data")
    assert.equal((await run(source, destination)).code, 1)
    assert.equal(
      await readFile(join(destination, "foreign.txt"), "utf8"),
      "preserve-existing-data"
    )
  })
})

test("a failed source read removes only the newly owned partial context", async () => {
  await scenario(async (source, destination, outside) => {
    await rm(join(source, "packages/sdk-typescript"), { recursive: true })
    assert.equal((await run(source, destination)).code, 1)
    assert.equal(await exists(destination), false)
    assert.equal(
      await readFile(join(outside, "secret.txt"), "utf8"),
      "private-context-test-secret"
    )
  })
})

test("root npm credentials cannot be copied or reflected as ordinary pnpm policy", async () => {
  await scenario(async (source, destination) => {
    await file(
      join(source, ".npmrc"),
      "engine-strict=true\n//registry.example.test/:_authToken=private-context-test-secret\n"
    )
    const result = await run(source, destination)
    assert.equal(result.code, 1)
    assert.equal(await exists(destination), false)
    assert.doesNotMatch(result.output, /private-context-test-secret/)
  })
})
