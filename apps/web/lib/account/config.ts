export type AccountConfig = {
  publicOrigin: string
  hydraOrigin: string
  apiInternalUrl: string
  kratosInternalUrl: string
  oidcFormActionOrigins: readonly string[]
}

export function isManagedLocalOrigin(origin: string): boolean {
  return /^http:\/\/127\.0\.0\.1:[1-9][0-9]{0,4}$/.test(origin)
}

function endpoint(
  value: string | undefined,
  kind: "https" | "managed-local" | "internal"
): string {
  if (!value || value !== value.trim() || /[\x00-\x20\x7f]/.test(value)) {
    throw new Error("Account origin configuration is unavailable.")
  }
  const url = new URL(value)
  const supported = {
    https: url.protocol === "https:",
    "managed-local": isManagedLocalOrigin(url.origin),
    internal: url.protocol === "http:" || url.protocol === "https:",
  }
  if (
    !supported[kind] ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash ||
    (value !== url.origin && value !== `${url.origin}/`)
  ) {
    throw new Error("Account origin configuration is unavailable.")
  }
  return url.origin
}

// This list permits configured native navigation, not OIDC discovery or identity trust.
function oidcFormActionOrigins(value: string | undefined): string[] {
  if (value === undefined) return []
  try {
    if (new TextEncoder().encode(value).byteLength > 4096) throw new Error()
    const entries: unknown = JSON.parse(value)
    if (!Array.isArray(entries) || entries.length > 8) throw new Error()
    const result: string[] = []
    for (const entry of entries) {
      if (typeof entry !== "string") throw new Error()
      const origin = endpoint(entry, "https")
      if (
        !/^https:\/\/(?:[a-z0-9.-]+|\[[a-f0-9:]+\])(?::[0-9]+)?$/i.test(
          origin
        ) ||
        result.includes(origin)
      )
        throw new Error()
      result.push(origin)
    }
    return result
  } catch {
    throw new Error("OIDC form navigation configuration is unavailable.")
  }
}

export function accountConfig(
  env: Readonly<Record<string, string | undefined>>
): AccountConfig {
  const transport = env.INFRAMELD_ACCOUNT_TRANSPORT ?? "https"
  if (transport !== "https" && transport !== "managed-local") {
    throw new Error("Account transport configuration is unavailable.")
  }
  const config = {
    publicOrigin: endpoint(env.INFRAMELD_ACCOUNT_PUBLIC_ORIGIN, transport),
    hydraOrigin: endpoint(env.INFRAMELD_ACCOUNT_HYDRA_ORIGIN, transport),
    apiInternalUrl: endpoint(
      env.INFRAMELD_ACCOUNT_API_INTERNAL_URL,
      "internal"
    ),
    kratosInternalUrl: endpoint(
      env.INFRAMELD_ACCOUNT_KRATOS_INTERNAL_URL,
      "internal"
    ),
    oidcFormActionOrigins: oidcFormActionOrigins(
      env.INFRAMELD_ACCOUNT_OIDC_FORM_ACTION_ORIGINS
    ),
  }
  if (config.publicOrigin === config.hydraOrigin) {
    throw new Error("Account and issuer routing must be distinct.")
  }
  return config
}

export function singleParameter(
  value: string | string[] | undefined,
  kind: "flow" | "challenge"
): string | undefined {
  if (value === undefined) return undefined
  if (
    typeof value !== "string" ||
    !value ||
    value.length > 4096 ||
    value.trim() !== value ||
    /[\x00-\x20\x7f]/.test(value) ||
    (kind === "flow" &&
      !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(value))
  ) {
    throw new Error("The sign-in request is invalid.")
  }
  return value
}

export function checkedProviderUrl(
  value: string,
  origin: string,
  path: string
): string {
  const url = new URL(value)
  // Local callers supply an origin validated by the server's managed profile.
  // Compare the original destination too, since URL parsing normalizes IPv4 aliases.
  const exactLocalDestination =
    isManagedLocalOrigin(origin) &&
    (value === `${origin}${path}` || value.startsWith(`${origin}${path}?`))
  if (
    value !== value.trim() ||
    /[\x00-\x20\x7f]/.test(value) ||
    url.origin !== origin ||
    (url.protocol !== "https:" && !exactLocalDestination) ||
    url.username ||
    url.password ||
    url.hash ||
    url.pathname !== path
  ) {
    throw new Error("The provider continuation could not be verified.")
  }
  return url.href
}
