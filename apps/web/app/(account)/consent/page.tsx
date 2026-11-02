import { headers } from "next/headers"
import { Stopped } from "../../../components/account/stopped"
import { accountConfig, singleParameter } from "../../../lib/account/config"
import { inspectConsent } from "../../../lib/account/consent"
import { ConsentForm } from "./consent-form"

export const dynamic = "force-dynamic"

export default async function ConsentPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  let loaded
  try {
    const config = accountConfig(process.env)
    const challenge = singleParameter(
      (await searchParams).consent_challenge,
      "challenge"
    )
    if (challenge) {
      const initialView = await inspectConsent({
        baseUrl: config.apiInternalUrl,
        challenge,
        cookie: (await headers()).get("cookie") ?? "",
      })
      loaded = { config, challenge, initialView }
    }
  } catch {}
  return (
    <>
      <h1 className="text-2xl font-semibold">CLI access</h1>
      {loaded ? (
        <ConsentForm
          initialView={loaded.initialView}
          challenge={loaded.challenge}
          publicOrigin={loaded.config.publicOrigin}
          hydraOrigin={loaded.config.hydraOrigin}
        />
      ) : (
        <Stopped />
      )}
    </>
  )
}
