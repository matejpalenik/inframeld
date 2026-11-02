import { accountConfig } from "./config"

// Native login starts at the account host and redirects through the fixed issuer.
export function accountContentSecurityPolicy(
  env: Readonly<Record<string, string | undefined>>
): string {
  const restricted =
    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
  try {
    const { hydraOrigin } = accountConfig(env)
    if (
      /^https:\/\/(?:[a-z0-9.-]+|\[[a-f0-9:]+\])(?::[0-9]+)?$/i.test(
        hydraOrigin
      )
    )
      return `${restricted} ${hydraOrigin}`
  } catch {}
  return restricted
}
