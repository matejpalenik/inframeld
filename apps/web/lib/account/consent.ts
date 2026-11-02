import {
  createClient,
  decideHumanOAuthConsent,
  inspectHumanOAuthConsent,
} from "@inframeld/sdk"
import type { HumanOAuthConsentDetailsResponse } from "@inframeld/sdk"
import { checkedProviderUrl } from "./config"

export type ConsentView =
  | { kind: "ready"; details: HumanOAuthConsentDetailsResponse }
  | { kind: "stopped"; message: string }

export type ConsentResult =
  | { kind: "continue"; redirectTo: string }
  | { kind: "stopped"; message: string; uncertain: boolean }

export type ConsentConnection = {
  baseUrl: string
  challenge: string
  cookie?: string
  fetch?: typeof globalThis.fetch
  signal?: AbortSignal
}

function client(connection: ConsentConnection) {
  return createClient({
    baseUrl: connection.baseUrl,
    credentials: "same-origin",
    cache: "no-store",
    timeoutMs: 12_000,
    throwOnError: false,
    responseStyle: "fields",
    headers:
      connection.cookie === undefined
        ? undefined
        : { Cookie: connection.cookie },
    fetch: connection.fetch,
  })
}

function stopped(status?: number): string {
  if (status === 401)
    return "Your browser session is unavailable. Restart sign-in from the requesting client."
  if (status === 403)
    return "This request cannot continue with the current account. Return to the requesting client to start again."
  if (status === 404)
    return "This sign-in request is no longer available. Start again from the requesting client."
  return "The sign-in request could not be checked. Return to the requesting client."
}

export async function inspectConsent(
  connection: ConsentConnection
): Promise<ConsentView> {
  const result = await inspectHumanOAuthConsent({
    client: client(connection),
    query: { consent_challenge: connection.challenge },
    signal: connection.signal,
  })
  if (result.data !== undefined && result.error === undefined)
    return { kind: "ready", details: result.data }
  return { kind: "stopped", message: stopped(result.response?.status) }
}

export async function decideConsent(
  connection: ConsentConnection,
  decision: "allow" | "deny",
  remember: boolean,
  hydraOrigin: string
): Promise<ConsentResult> {
  const result = await decideHumanOAuthConsent({
    client: client(connection),
    body: {
      consentChallenge: connection.challenge,
      decision,
      remember: decision === "allow" && remember,
    },
    headers: { "X-Inframeld-CSRF": "1" },
    signal: connection.signal,
  })
  if (result.data !== undefined && result.error === undefined) {
    try {
      return {
        kind: "continue",
        redirectTo: checkedProviderUrl(
          result.data.redirectTo,
          hydraOrigin,
          "/oauth2/auth"
        ),
      }
    } catch {
      // Approval may already exist. Do not repeat the mutation to repair its response.
    }
  }
  const uncertain =
    !result.response ||
    result.response.status >= 500 ||
    result.error?.kind === "decode" ||
    result.error?.kind === "transport" ||
    result.data !== undefined
  return {
    kind: "stopped",
    message: uncertain
      ? "The decision outcome could not be confirmed. Do not submit it again. Return to the requesting client."
      : stopped(result.response?.status),
    uncertain,
  }
}
