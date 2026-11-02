// Private process substitute. This file never invokes a container runtime.
import { appendFileSync, readFileSync, writeFileSync } from "node:fs"
import { join } from "node:path"
import { spawn, execFileSync } from "node:child_process"
const directory = process.env.ACCOUNT_PROBE_DIRECTORY
if (!directory) throw new Error("A private probe directory is required.")
const args = process.argv.slice(2)
// This last-resort containment fires after every cleanup assertion deadline.
setTimeout(() => {
  writeFileSync(join(directory, "fuse-fired"), "fixture self-expired\n")
  process.exit(99)
}, 30_000).unref()
const group = Number(
  execFileSync("ps", ["-o", "pgid=", "-p", String(process.pid)], {
    encoding: "utf8",
    timeout: 1_000,
    maxBuffer: 4_096,
  }).trim()
)
appendFileSync(
  join(directory, "processes.jsonl"),
  JSON.stringify({ pid: process.pid, group }) + "\n"
)
const globalVolumes =
  args[0] === "volume" && args[1] === "ls" && !args.includes("--filter")
const startup = process.env.ACCOUNT_PROBE_STARTUP === "true"
const operationIndex = args.findIndex((arg) =>
  ["up", "run", "exec"].includes(arg)
)
const operation = operationIndex < 0 ? undefined : args[operationIndex]
const operands = args
  .slice(operationIndex + 1)
  .filter((arg) => !arg.startsWith("-"))
const service = operands[0]
const startupHang =
  startup &&
  operation === "run" &&
  service === process.env.ACCOUNT_PROBE_STARTUP_HANG
const kind =
  args[0] === "probe-phase"
    ? "phase"
    : args[0] === "probe-descendant"
      ? "descendant"
      : args.includes("down")
        ? "down"
        : args.includes("ps") || args.includes("ls")
          ? "inventory"
          : args.includes("inspect")
            ? "inspect"
            : "engine"
appendFileSync(
  join(directory, "events.jsonl"),
  JSON.stringify({ kind, args }) + "\n"
)
const hanging =
  kind === "descendant" ||
  (kind === "phase" && process.env.ACCOUNT_PROBE_PHASE === "hang") ||
  (kind === "down" && process.env.ACCOUNT_PROBE_CLEANUP === "hang") ||
  (kind === "inventory" && process.env.ACCOUNT_PROBE_INVENTORY === "hang") ||
  (globalVolumes && process.env.ACCOUNT_PROBE_VOLUME_INVENTORY === "hang") ||
  startupHang
const naturalDescendant =
  kind === "phase" &&
  ["exit-with-descendant", "exit-with-closed-descendant"].includes(
    process.env.ACCOUNT_PROBE_PHASE
  )
if (naturalDescendant) {
  spawn(process.execPath, [process.argv[1], "probe-descendant"], {
    stdio:
      process.env.ACCOUNT_PROBE_PHASE === "exit-with-closed-descendant"
        ? "ignore"
        : "inherit",
    env: process.env,
  }).unref()
  const deadline = Date.now() + 5_000
  while (Date.now() < deadline) {
    try {
      readFileSync(join(directory, "descendant-ready"))
      process.exit(0)
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 10))
  }
  process.exit(98)
} else if (hanging) {
  process.on("SIGTERM", () => {})
  if (kind !== "descendant")
    spawn(process.execPath, [process.argv[1], "probe-descendant"], {
      stdio: "ignore",
      env: process.env,
    }).unref()
  writeFileSync(
    join(directory, `${startupHang ? "startup" : kind}-ready`),
    String(process.pid)
  )
  setInterval(() => {}, 1_000)
} else if (startup && operation) {
  // Model fresh fixture lifetimes and socket-only temporary Postgres startup.
  // This state machine never opens a network connection or invokes a provider.
  const stateFile = join(directory, "startup-state.json")
  let state = {
    initialized: [],
    completed: [],
    started: [],
    tcpReady: [],
    checks: {},
  }
  try {
    state = JSON.parse(readFileSync(stateFile, "utf8"))
  } catch {}
  let failure = 0
  const reject = () => {
    failure = 61
  }
  const initialize = (name) => {
    if (state.initialized.includes(name)) {
      failure = 62
      return
    }
    state.initialized.push(name)
  }
  if (operation === "run") {
    if (service === process.env.ACCOUNT_PROBE_STARTUP_FAIL) failure = 23
    else if (["account-tls-init", "breach-tls-init"].includes(service))
      initialize(service)
    else {
      const migrationDatabase = {
        "hydra-migrate": "hydra-postgres",
        "kratos-migrate": "kratos-postgres",
        migrate: "postgres",
      }[service]
      if (migrationDatabase && !state.tcpReady.includes(migrationDatabase))
        reject()
      if (service === "oauth-client-setup" && !state.started.includes("hydra"))
        reject()
      if (service === "identity-setup" && !state.started.includes("kratos"))
        reject()
      if (
        service === "seed" &&
        !["migrate", "oauth-client-setup", "identity-setup"].every((name) =>
          state.completed.includes(name)
        )
      )
        reject()
      if (!failure) state.completed.push(service)
    }
  } else if (operation === "up") {
    if (!args.includes("--no-deps") && operands.includes("gateway")) {
      initialize("account-tls-init")
      initialize("account-tls-init")
    }
    for (const name of operands) {
      if (
        name === "password-breaches" &&
        !state.initialized.includes("breach-tls-init")
      )
        reject()
      if (name === "hydra" && !state.completed.includes("hydra-migrate"))
        reject()
      if (
        name === "kratos" &&
        !["kratos-migrate"].every((entry) => state.completed.includes(entry))
      )
        reject()
      if (name === "backend" && !state.completed.includes("seed")) reject()
      if (
        name === "gateway" &&
        (!state.initialized.includes("account-tls-init") ||
          !["backend", "web"].every((entry) => state.started.includes(entry)))
      )
        reject()
      if (!failure) state.started.push(name)
    }
  } else if (operation === "exec") {
    if (!state.started.includes(service)) reject()
    const count = (state.checks[service] ?? 0) + 1
    state.checks[service] = count
    const host = args[args.indexOf("-h") + 1]
    if (host === "127.0.0.1") {
      if (count === 1) failure = 1
      else state.tcpReady.push(service)
    }
    // A socket-only temporary server deliberately returns0 but cannot authorize migration.
  }
  writeFileSync(stateFile, JSON.stringify(state))
  process.exitCode = failure
} else if (globalVolumes) {
  const countFile = join(directory, "volume-inventory-count")
  let count = 0
  try {
    count = Number(readFileSync(countFile, "utf8"))
  } catch {}
  writeFileSync(countFile, String(count + 1))
  const baseline = process.env.ACCOUNT_PROBE_MAIN === "true" && count === 0
  const mode = baseline
    ? process.env.ACCOUNT_PROBE_BASELINE
    : process.env.ACCOUNT_PROBE_VOLUME_INVENTORY
  if (mode !== "fail") {
    console.log("original-a")
    if (mode !== "missing" && mode !== "partial")
      console.log("original-b\noriginal-a")
    if (mode === "leak") console.log("unexplained-anonymous-volume")
  }
  if (mode === "fail" || mode === "partial") process.exitCode = 37
} else if (kind === "phase")
  process.exitCode = Number(process.env.ACCOUNT_PROBE_STATUS ?? "0")
else if (kind === "down")
  process.exitCode = Number(process.env.ACCOUNT_PROBE_CLEANUP_STATUS ?? "0")
else if (
  kind === "inventory" &&
  process.env.ACCOUNT_PROBE_INVENTORY === "remaining"
)
  console.log("controlled-owned-resource")
else if (kind === "inspect") process.exitCode = 1
