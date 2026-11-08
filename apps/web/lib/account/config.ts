export type AccountConfig = {
  publicOrigin: string
  hydraOrigin: string
  apiInternalUrl: string
  kratosInternalUrl: string
  oidcFormActionOrigins: readonly string[]
}

function endpoint(value: string | undefined, publicEndpoint: boolean): string {
  if (!value || value !== value.trim() || /[\x00-\x20\x7f]/.test(value)) {
    throw new Error("Account HTTPS configuration is unavailable.")
  }
  const url = new URL(value)
  if (
    (publicEndpoint
      ? url.protocol !== "https:"
      : !["http:", "https:"].includes(url.protocol)) ||
    url.username ||
    url.password ||
    url.pathname !== "/" ||
    url.search ||
    url.hash ||
    (value !== url.origin && value !== `${url.origin}/`)
  ) {
    throw new Error("Account HTTPS configuration is unavailable.")
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
      const origin = endpoint(entry, true)
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
  const config = {
    publicOrigin: endpoint(env.INFRAMELD_ACCOUNT_PUBLIC_ORIGIN, true),
    hydraOrigin: endpoint(env.INFRAMELD_ACCOUNT_HYDRA_ORIGIN, true),
    apiInternalUrl: endpoint(env.INFRAMELD_ACCOUNT_API_INTERNAL_URL, false),
    kratosInternalUrl: endpoint(
      env.INFRAMELD_ACCOUNT_KRATOS_INTERNAL_URL,
      false
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
  if (
    value !== value.trim() ||
    /[\x00-\x20\x7f]/.test(value) ||
    url.origin !== origin ||
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.hash ||
    url.pathname !== path
  ) {
    throw new Error("The provider continuation could not be verified.")
  }
  return url.href
}
