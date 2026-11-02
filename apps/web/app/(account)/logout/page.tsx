import { headers } from "next/headers"
import { Stopped } from "../../../components/account/stopped"
import { accountConfig } from "../../../lib/account/config"
import { browserLogoutUrl } from "../../../lib/account/kratos"

export const dynamic = "force-dynamic"

export default async function LogoutPage() {
  let target
  try {
    const config = accountConfig(process.env)
    target = await browserLogoutUrl(
      config,
      (await headers()).get("cookie") ?? ""
    )
  } catch {}
  return (
    <>
      <h1 className="text-2xl font-semibold">Sign out of this browser</h1>
      {target ? (
        <>
          <p>
            This ends the browser session. Existing CLI credentials have their
            own lifetime and are not revoked by this action.
          </p>
          <a
            href={target}
            className="inline-flex min-h-11 items-center rounded-md border px-4 py-2 font-medium"
          >
            Sign out of browser
          </a>
        </>
      ) : (
        <Stopped message="A browser sign-out could not be prepared. Your browser session may already have ended. Return to the requesting client." />
      )}
    </>
  )
}
