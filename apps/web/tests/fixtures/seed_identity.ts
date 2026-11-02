import { randomBytes } from "node:crypto"
import { writeFile } from "node:fs/promises"
import { setTimeout } from "node:timers/promises"
import { Configuration, IdentityApi } from "@ory/client-fetch"

// Setup creates an existing fixture human before the browser journey. It never approves OAuth.
async function main() {
  const transport: typeof fetch = (input, init) =>
    fetch(input, {
      ...init,
      redirect: "error",
      signal: AbortSignal.timeout(8_000),
    })
  const api = new IdentityApi(
    new Configuration({ basePath: "http://kratos:4434", fetchApi: transport })
  )
  const deadline = Date.now() + 60_000
  while (true) {
    try {
      await api.listIdentities({ pageSize: 1 })
      break
    } catch {
      if (Date.now() >= deadline)
        throw new Error("Provider setup did not become ready.")
      await setTimeout(250)
    }
  }
  const email = `account-${randomBytes(12).toString("hex")}@example.test`
  const password = `Native-${randomBytes(24).toString("hex")}!`
  const identity = await api.createIdentity({
    createIdentityBody: {
      schema_id: "default",
      state: "active",
      traits: { email },
      credentials: { password: { config: { password } } },
    },
  })
  const checked = await api.getIdentity({
    id: identity.id,
    includeCredential: ["password", "code"],
  })
  if (!checked.credentials?.password || !checked.credentials.code)
    throw new Error("Existing password/code credentials were not established.")
  await writeFile(
    "/run/account-fixture/human.json",
    JSON.stringify({ subject: identity.id, email, password }),
    { mode: 0o600, flag: "wx" }
  )
}
main().catch(() => {
  console.error(
    "Existing-human fixture setup failed. No browser qualification ran."
  )
  process.exitCode = 1
})
