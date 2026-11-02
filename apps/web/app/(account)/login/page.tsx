import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { KratosFlowForm } from "../../../components/account/kratos-flow-form"
import { Stopped } from "../../../components/account/stopped"
import { accountConfig, singleParameter } from "../../../lib/account/config"
import { readLoginFlow } from "../../../lib/account/kratos"

export const dynamic = "force-dynamic"

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  let config
  let flowId
  try {
    config = accountConfig(process.env)
    flowId = singleParameter((await searchParams).flow, "flow")
  } catch {
    return (
      <>
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <Stopped />
      </>
    )
  }
  if (!flowId) redirect(`${config.publicOrigin}/self-service/login/browser`)
  let flow
  try {
    flow = await readLoginFlow(
      config,
      flowId,
      (await headers()).get("cookie") ?? ""
    )
  } catch {
    return (
      <>
        <h1 className="text-2xl font-semibold">Sign in</h1>
        <Stopped message="This browser sign-in flow expired or could not be checked. Restart sign-in from the requesting client." />
      </>
    )
  }
  return (
    <>
      <h1 className="text-2xl font-semibold">Sign in to Inframeld</h1>
      <p>
        Use an existing account. This page cannot create an account or grant
        installation access.
      </p>
      <KratosFlowForm
        ui={flow.ui}
        flowId={flowId}
        publicOrigin={config.publicOrigin}
      />
    </>
  )
}
