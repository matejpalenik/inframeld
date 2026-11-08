import type {
  InvitationActivationResponse,
  InvitationPreviewResponse,
} from "@inframeld/sdk"
import {
  activateInvitation,
  createClient,
  previewInvitation,
} from "@inframeld/sdk"
import { readCurrentIdentity } from "./kratos"

export type InvitationConnection = {
  publicOrigin: string
  fetch?: typeof globalThis.fetch
  signal?: AbortSignal
}

/** Retain only in this page, under the identity that made the explicit decision. */
export type InvitationOriginal = Readonly<{
  identityId: string
  token: string
  key: string
  method: "POST"
  route: "/v1/invitations/activate"
}>

type InvitationStopped =
  { kind: "stopped"; message: string } | { kind: "identity-changed" }

export type InvitationPreview =
  | {
      kind: "ready"
      identityId: string
      preview: InvitationPreviewResponse
    }
  | InvitationStopped

export type InvitationActivation =
  | { kind: "completed"; receipt: InvitationActivationResponse }
  | { kind: "uncertain"; message: string }
  | InvitationStopped

export function invitationOriginal(
  identityId: string,
  token: string,
  key: string
): InvitationOriginal {
  if (
    !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(identityId) ||
    !/^[A-Za-z0-9_-]{43}$/.test(token) ||
    !key.trim() ||
    key.trim() !== key ||
    key.length > 128 ||
    /[\r\n]/.test(key)
  )
    throw new Error("Use a valid identity, protected token and original key.")
  return Object.freeze({
    identityId,
    token,
    key,
    method: "POST",
    route: "/v1/invitations/activate",
  })
}

function budget(connection: InvitationConnection): AbortSignal {
  connection.signal?.throwIfAborted()
  return AbortSignal.any([
    AbortSignal.timeout(8_000),
    ...(connection.signal ? [connection.signal] : []),
  ])
}

function identity(connection: InvitationConnection, signal: AbortSignal) {
  return readCurrentIdentity(
    { kratosInternalUrl: connection.publicOrigin },
    undefined,
    connection.fetch,
    signal
  )
}

function client(connection: InvitationConnection) {
  return createClient({
    baseUrl: connection.publicOrigin,
    credentials: "same-origin",
    cache: "no-store",
    timeoutMs: 5_000,
    throwOnError: false,
    responseStyle: "fields",
    fetch: connection.fetch,
  })
}

function message(status?: number): string {
  if (status === 401)
    return "Sign in with your browser identity before continuing."
  if (status === 403)
    return "This request cannot continue with the current account. This page cannot determine or clear the restriction."
  if (status === 404)
    return "This invitation is not available for a new activation. For an uncertain original activation, use its saved token and key to recover the original result."
  if (status === 409)
    return "The current account or intended assignments cannot activate this invitation. No new access is confirmed."
  return "The invitation could not be checked. No new access is confirmed."
}

const uncertain = {
  kind: "uncertain" as const,
  message:
    "The activation outcome is unknown. Cancellation does not prove rollback. Preserve the exact original token and key, then explicitly recover under the same identity.",
}

export async function currentInvitationIdentity(
  connection: InvitationConnection
): Promise<string | null> {
  return identity(connection, budget(connection))
}

export async function inspectInvitation(
  connection: InvitationConnection,
  token: string
): Promise<InvitationPreview> {
  const signal = budget(connection)
  if (!/^[A-Za-z0-9_-]{43}$/.test(token))
    return { kind: "stopped", message: "Enter the protected invitation token." }
  try {
    const before = await identity(connection, signal)
    if (before === null) return { kind: "stopped", message: message(401) }
    const result = await previewInvitation({
      client: client(connection),
      body: { invitationToken: token },
      headers: { "X-Inframeld-CSRF": "1" },
      signal,
    })
    const after = await identity(connection, signal)
    signal.throwIfAborted()
    if (before !== after) return { kind: "identity-changed" }
    return result.data !== undefined && result.error === undefined
      ? { kind: "ready", identityId: before, preview: result.data }
      : { kind: "stopped", message: message(result.response?.status) }
  } catch {
    connection.signal?.throwIfAborted()
    return { kind: "stopped", message: message() }
  }
}

export async function activateOriginalInvitation(
  connection: InvitationConnection,
  original: InvitationOriginal
): Promise<InvitationActivation> {
  const signal = budget(connection)
  // Recovery has exactly the original operation binding. Never preview it first.
  invitationOriginal(original.identityId, original.token, original.key)
  if (
    original.method !== "POST" ||
    original.route !== "/v1/invitations/activate"
  )
    throw new Error("Use the exact original activation request.")
  let dispatched = false
  try {
    const before = await identity(connection, signal)
    if (before !== original.identityId) return { kind: "identity-changed" }
    signal.throwIfAborted()
    dispatched = true
    const result = await activateInvitation({
      client: client(connection),
      body: { invitationToken: original.token },
      headers: {
        "X-Inframeld-CSRF": "1",
        "Idempotency-Key": original.key,
      },
      signal,
    })
    const after = await identity(connection, signal)
    signal.throwIfAborted()
    if (after !== original.identityId) return { kind: "identity-changed" }
    if (result.data !== undefined && result.error === undefined)
      return { kind: "completed", receipt: result.data }
    if (
      !result.response ||
      result.response.status >= 500 ||
      result.error?.kind === "decode" ||
      result.error?.kind === "transport"
    )
      return uncertain
    return { kind: "stopped", message: message(result.response.status) }
  } catch {
    if (dispatched) return uncertain
    connection.signal?.throwIfAborted()
    return {
      kind: "stopped",
      message:
        "Your current browser identity could not be verified. No activation was sent.",
    }
  }
}
