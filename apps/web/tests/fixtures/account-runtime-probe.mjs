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
const proof = process.env.ACCOUNT_PROBE_PROOF ?? ""
const operationIndex = args.findIndex((arg) =>
  ["up", "run", "exec"].includes(arg)
)
const operation = operationIndex < 0 ? undefined : args[operationIndex]
const operands = args
  .slice(operationIndex + 1)
  .filter((arg) => !arg.startsWith("-"))
const service = operands[0]
const proofServices = ["browser-tests", "proof-driver", "proof-denied-driver"]
const lookupService =
  args[0] === "ps"
    ? args
        .find((arg) => arg.startsWith("label=com.docker.compose.service="))
        ?.slice("label=com.docker.compose.service=".length)
    : undefined
const unsupportedComposeLookup =
  args[0] === "compose" &&
  args.includes("ps") &&
  proofServices.includes(args.at(-1))
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
} else if (proof && unsupportedComposeLookup) {
  // Podman Compose 1.5 rejects service operands for ps before querying the engine.
  process.exitCode = 2
} else if (
  proof &&
  (args.includes("inspect") ||
    args.includes("logs") ||
    proofServices.includes(lookupService) ||
    (operation === "up" &&
      ["browser-tests", "proof-driver", "proof-denied-driver"].includes(
        service
      )) ||
    (operation === "exec" &&
      (args.includes("verify-proof-result") ||
        args.includes("verify-denied-result") ||
        service === "browser-tests")))
) {
  // Closed observations for the existing owner's combined flow. No engine is called.
  const stateFile = join(directory, "proof-state.json")
  let state = {
    browser: false,
    denied: false,
    negativeVerified: false,
    driver: false,
    observations: 0,
  }
  try {
    state = JSON.parse(readFileSync(stateFile, "utf8"))
  } catch {}
  const browser = "b".repeat(64)
  const driver = "d".repeat(64)
  const denied = "e".repeat(64)
  if (operation === "up") {
    if (service === "browser-tests") state.browser = true
    else if (service === "proof-denied-driver") state.denied = true
    else state.driver = true
  } else if (lookupService) {
    const project = process.env.INFRAMELD_ACCOUNT_WEB_IMAGE.slice(
      "localhost/".length,
      -"-web:check".length
    )
    const projectLabel = args.find(
      (arg) =>
        arg.startsWith("label=com.docker.compose.project=") ||
        arg.startsWith("label=io.podman.compose.project=")
    )
    if (
      !args.includes("--no-trunc") ||
      ![
        `label=com.docker.compose.project=${project}`,
        `label=io.podman.compose.project=${project}`,
      ].includes(projectLabel)
    )
      process.exitCode = 58
    else if (
      proof === "lookup-query-failed" &&
      projectLabel.startsWith("label=com.docker.compose.project=")
    )
      process.exitCode = 57
    else {
      const id =
        lookupService === "browser-tests"
          ? browser
          : lookupService === "proof-denied-driver"
            ? denied
            : driver
      if (proof === "lookup-multiple") console.log(`${id}\n${"f".repeat(64)}`)
      else if (proof === "lookup-truncated") console.log(id.slice(0, 12))
      else if (
        proof === "lookup-reused-browser" &&
        lookupService === "proof-driver"
      )
        console.log(browser)
      else if (proof !== "lookup-zero") console.log(id)
    }
  } else if (args.includes("inspect")) {
    state.observations += 1
    if (proof === "inspect-invalid") console.log("not-json")
    else {
      const id = args.at(-1)
      const isBrowser = id === browser
      const isDenied = id === denied
      const status =
        (isDenied && proof !== "denied-stalled") ||
        (isBrowser && proof === "browser-failed")
          ? "exited"
          : state.driver && proof !== "stalled-terminal"
            ? "exited"
            : "running"
      console.log(
        JSON.stringify({
          Id:
            proof === "wrong-id" || (isDenied && proof === "denied-wrong-id")
              ? "f".repeat(64)
              : id,
          Config: {
            User: "10001:10001",
            Labels: {
              "com.docker.compose.project":
                proof === "lookup-wrong-project"
                  ? "another-project"
                  : process.env.INFRAMELD_ACCOUNT_WEB_IMAGE.slice(
                      "localhost/".length,
                      -"-web:check".length
                    ),
              "com.docker.compose.service":
                proof === "lookup-wrong-service"
                  ? "another-service"
                  : isBrowser
                    ? "browser-tests"
                    : isDenied
                      ? "proof-denied-driver"
                      : "proof-driver",
            },
          },
          HostConfig: {
            Privileged: false,
            Init: true,
            PidMode: "",
            NetworkMode:
              isDenied && proof === "denied-host-net"
                ? "host"
                : isBrowser
                  ? "account-private"
                  : `container:${browser}`,
          },
          State: {
            Status: status,
            ExitCode: isDenied
              ? proof === "denied-wrong-exit"
                ? 0
                : 1
              : isBrowser && proof === "browser-failed"
                ? 8
                : !isBrowser &&
                    ["driver-failed", "driver-logs-failed"].includes(proof)
                  ? 7
                  : 0,
            Health: {
              Status:
                proof === "unhealthy"
                  ? "unhealthy"
                  : proof === "never-ready"
                    ? "starting"
                    : "healthy",
            },
          },
        })
      )
    }
  } else if (args.includes("logs")) {
    const id = args.at(-1)
    if (id === browser) console.log("controlled browser diagnostic")
    else if (id === denied && proof === "denied-wrong-exit")
      console.log("controlled denied diagnostic")
    else if (
      id === driver &&
      ["driver-failed", "driver-logs-failed"].includes(proof)
    ) {
      console.log("controlled allowed diagnostic")
      if (proof === "driver-logs-failed") process.exitCode = 43
    } else
      console.log(
        id === denied
          ? '{"schemaVersion":1,"error":{"kind":"denied","resourceCleanup":"not-needed","credentialCleanup":"not-needed"}}'
          : '{"schemaVersion":1,"result":{}}'
      )
  } else if (operation === "exec") {
    if (service === "browser-tests") {
      const profile = args.indexOf("--profile")
      process.exitCode =
        profile < 0 || args[profile + 1] !== "qualification"
          ? 1
          : proof === "second-readiness-failed"
            ? 17
            : state.negativeVerified
              ? 0
              : 10
    } else if (args.includes("verify-denied-result")) {
      if (proof === "denied-effects") process.exitCode = 25
      else state.negativeVerified = true
    } else process.exitCode = proof === "verify-failed" ? 25 : 0
  }
  if (!args.includes("logs")) writeFileSync(stateFile, JSON.stringify(state))
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
