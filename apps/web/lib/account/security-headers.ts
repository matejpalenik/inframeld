import { accountConfig, isManagedLocalOrigin } from "./config"

// Native login starts at the account host and redirects through the fixed issuer.
export function accountContentSecurityPolicy(
  env: Readonly<Record<string, string | undefined>>
): string {
  const restricted =
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
  try {
    const { hydraOrigin, oidcFormActionOrigins } = accountConfig(env)
    if (
      isManagedLocalOrigin(hydraOrigin) ||
      /^https:\/\/(?:[a-z0-9.-]+|\[[a-f0-9:]+\])(?::[0-9]+)?$/i.test(
        hydraOrigin
      )
    )
      return [restricted, hydraOrigin, ...oidcFormActionOrigins].join(" ")
  } catch {}
  return restricted
}
