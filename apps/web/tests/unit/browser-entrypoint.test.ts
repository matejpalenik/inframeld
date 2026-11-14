import assert from "node:assert/strict"
import { spawnSync } from "node:child_process"
import {
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  readlink,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises"
import { tmpdir } from "node:os"
import { join, resolve } from "node:path"
import { test } from "node:test"

// These finite commands model trust-store effects. They run no NSS or browser.
const command = String.raw`
const fs = require("node:fs");
const path = require("node:path");
const args = process.argv.slice(2);
const database = path.join(process.env.HOME, ".local/share/pki/nssdb");
const initialized = path.join(database, "initialized");
const imported = path.join(database, "imported");
const certutil = path.basename(process.argv[1]) === "certutil";
const stage = certutil
  ? args.includes("-N") ? "initialize" : args.includes("-A") ? "import" : "readback"
  : args.includes("tests/fixtures/check-untrusted.ts") ? "untrusted" : "suite";
fs.appendFileSync(process.env.ACCOUNT_COMMAND_EVENTS, stage + "\n");
if (stage === "untrusted" && !fs.existsSync(initialized)) process.exit(41);
if (stage === "untrusted" && fs.existsSync(imported)) process.exit(42);
if (stage === "initialize" && fs.existsSync(initialized)) process.exit(43);
if (["import", "readback", "suite"].includes(stage) && !fs.existsSync(initialized)) process.exit(44);
if (["readback", "suite"].includes(stage) && !fs.existsSync(imported)) process.exit(45);
if (fs.readFileSync(0).length !== 0) process.exit(46);
if (process.env.ACCOUNT_COMMAND_FAILURE === stage) process.exit(17);
if (stage === "initialize") fs.writeFileSync(initialized, "empty-password\n");
if (stage === "import") fs.writeFileSync(imported, "fixture-ca\n");
if (stage === "suite") console.log(JSON.stringify(args));
`

async function fixture(
  check: (state: {
    home: string
    run: (options?: {
      failure?: string
      xdg?: string
      proofMode?: string
    }) => Promise<{
      status: number | null
      events: string[]
      stdout: string
    }>
  }) => Promise<void>
) {
  const directory = await mkdtemp(join(tmpdir(), "account-nss-entrypoint-"))
  const home = join(directory, "home")
  const bin = join(directory, "bin")
  const events = join(directory, "events")
  await mkdir(home)
  await mkdir(bin)
  for (const name of ["node", "certutil"])
    await writeFile(join(bin, name), `#!${process.execPath}\n${command}`, {
      mode: 0o700,
    })
  try {
    await check({
      home,
      async run(options = {}) {
        const child = spawnSync(
          "/bin/bash",
          [resolve("tests/fixtures/browser-entrypoint.sh")],
          {
            cwd: process.cwd(),
            env: {
              ...process.env,
              HOME: home,
              PATH: `${bin}:/usr/bin:/bin`,
              XDG_DATA_HOME: options.xdg ?? "",
              ACCOUNT_COMMAND_EVENTS: events,
              ACCOUNT_COMMAND_FAILURE: options.failure ?? "",
              INFRAMELD_ACCOUNT_PROOF_MODE: options.proofMode ?? "0",
            },
            encoding: "utf8",
            input: "Input must not become a password answer.\n",
            timeout: 3_000,
            maxBuffer: 16_384,
          }
        )
        // Completion must precede the containment timeout and private-file removal.
        assert.equal(
          child.error,
          undefined,
          "Entrypoint exceeded its owned bound"
        )
        assert.equal(
          child.signal,
          null,
          "The containment fuse must not stop the entrypoint"
        )
        let observed: string[] = []
        try {
          observed = (await readFile(events, "utf8")).trim().split("\n")
        } catch (error) {
          if (!(
            error instanceof Error &&
            "code" in error &&
            error.code === "ENOENT"
          ))
            throw error
        }
        return { status: child.status, events: observed, stdout: child.stdout }
      },
    })
  } finally {
    await rm(directory, { recursive: true, force: true })
  }
}

test("fresh NSS initialization precedes untrusted Chromium and CA import with closed stdin", async () => {
  await fixture(async ({ home, run }) => {
    const result = await run()
    assert.equal(result.status, 0)
    assert.deepEqual(result.events, [
      "initialize",
      "untrusted",
      "import",
      "readback",
      "suite",
    ])
    assert.equal(
      await readFile(join(home, ".local/share/pki/nssdb/initialized"), "utf8"),
      "empty-password\n"
    )
  })
})

for (const proofMode of ["0", "bootstrap"]) {
  test(`browser mode ${proofMode} runs only its supported test files`, async () => {
    await fixture(async ({ run }) => {
      const result = await run({ proofMode })
      assert.equal(result.status, 0)
      const bootstrap = "native-bootstrap-proof.test.ts"
      const expected =
        proofMode === "bootstrap"
          ? [bootstrap]
          : (await readdir("tests/browser")).filter(
              (name) => name.endsWith(".test.ts") && name !== bootstrap
            )
      const args: string[] = JSON.parse(
        result.stdout.trim().split("\n").at(-1)!
      )
      assert.deepEqual(args.slice(0, 4), [
        "--import",
        "tsx",
        "--test",
        "--test-concurrency=1",
      ])
      assert.deepEqual(
        args.slice(4).sort(),
        expected.map((name) => `tests/browser/${name}`).sort()
      )
    })
  })
}

for (const location of [".pki/nssdb", ".local/share/pki/nssdb"]) {
  for (const kind of ["directory", "file", "dangling-link"] as const) {
    test(`preexisting ${location} ${kind} is preserved before any trust or browser command`, async () => {
      await fixture(async ({ home, run }) => {
        const database = join(home, location)
        await mkdir(resolve(database, ".."), { recursive: true })
        const retained = join(home, "retained")
        if (kind === "directory") {
          await mkdir(database)
          await writeFile(join(database, "retained"), "original")
        } else if (kind === "file") await writeFile(database, "original")
        else await symlink(retained, database)
        const result = await run()
        assert.notEqual(result.status, 0)
        assert.deepEqual(result.events, [])
        if (kind === "directory")
          assert.equal(
            await readFile(join(database, "retained"), "utf8"),
            "original"
          )
        else if (kind === "file")
          assert.equal(await readFile(database, "utf8"), "original")
        else {
          assert.equal(await readlink(database), retained)
        }
      })
    })
  }
}

test("an unexpected XDG trust location stops before any command", async () => {
  await fixture(async ({ home, run }) => {
    const result = await run({ xdg: join(home, "other") })
    assert.notEqual(result.status, 0)
    assert.deepEqual(result.events, [])
  })
})

test("the canonical XDG data location retains the same fresh trust sequence", async () => {
  await fixture(async ({ home, run }) => {
    const result = await run({ xdg: join(home, ".local/share") })
    assert.equal(result.status, 0)
    assert.equal(result.events.at(-1), "suite")
  })
})

const stages = ["initialize", "untrusted", "import", "readback"]
for (const [index, stage] of stages.entries()) {
  test(`${stage} failure prevents downstream trust and browser effects`, async () => {
    await fixture(async ({ run }) => {
      const result = await run({ failure: stage })
      assert.equal(result.status, 17)
      assert.deepEqual(result.events, stages.slice(0, index + 1))
    })
  })
}
