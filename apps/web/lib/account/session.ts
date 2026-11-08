import { createClient, getCurrentSession } from "@inframeld/sdk"
import { readCurrentIdentity } from "./kratos"

export type AccountView =
  | { kind: "signed-out" }
  | { kind: "unavailable" }
  | { kind: "changed" }
  | {
      kind: "verified"
      identityId: string
      access:
        | { kind: "admitted"; principalId: string }
        | { kind: "denied" }
        | { kind: "unavailable" }
    }

export type AccountConnection = {
  baseUrl: string
  kratosUrl: string
  cookie?: string
  fetch?: typeof globalThis.fetch
  signal?: AbortSignal
}

export async function inspectAccount(
  connection: AccountConnection
): Promise<AccountView> {
  connection.signal?.throwIfAborted()
  const signal = AbortSignal.any([
    AbortSignal.timeout(8_000),
    ...(connection.signal ? [connection.signal] : []),
  ])
  try {
    const configured = { kratosInternalUrl: connection.kratosUrl }
    const identity = await readCurrentIdentity(
      configured,
      connection.cookie,
      connection.fetch,
      signal
    )
    if (identity === null) return { kind: "signed-out" }
    const local = await getCurrentSession({
      client: createClient({
        baseUrl: connection.baseUrl,
        credentials: "same-origin",
        cache: "no-store",
        timeoutMs: 8_000,
        throwOnError: false,
        responseStyle: "fields",
        headers:
          connection.cookie === undefined
            ? undefined
            : { Cookie: connection.cookie },
        fetch: connection.fetch,
      }),
      signal,
    })
    // A changed browser cannot inherit details from the preceding product read.
    const current = await readCurrentIdentity(
      configured,
      connection.cookie,
      connection.fetch,
      signal
    )
    signal.throwIfAborted()
    if (current === null) return { kind: "signed-out" }
    if (current !== identity) return { kind: "changed" }
    return {
      kind: "verified",
      identityId: identity,
      access:
        local.data !== undefined && local.error === undefined
          ? { kind: "admitted", principalId: local.data.principalId }
          : local.response?.status === 403
            ? { kind: "denied" }
            : { kind: "unavailable" },
    }
  } catch {
    connection.signal?.throwIfAborted()
    return { kind: "unavailable" }
  }
}
