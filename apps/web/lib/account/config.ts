export type AccountConfig = {
  publicOrigin: string
  hydraOrigin: string
  apiInternalUrl: string
  kratosInternalUrl: string
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
