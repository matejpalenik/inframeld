import Link from "next/link"
import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { loadAccountFlow } from "../../lib/account/flow-page"
import type { NativeAccountFlowKind } from "../../lib/account/flow-page"
import { KratosFlowForm } from "./kratos-flow-form"
import { Stopped } from "./stopped"

const descriptions = {
  registration: {
    title: "Create your identity",
    text: "Create an account with the configured identity provider. This does not admit you to Inframeld or grant installation access.",
  },
  verification: {
    title: "Verify your email address",
    text: "Complete the identity provider's verification step. A verified email does not link accounts or grant Inframeld access.",
  },
  recovery: {
    title: "Recover your account",
    text: "After the recovery code, finish password settings. Required security cleanup and any invitation activation are separate steps. This page cannot release an access block.",
  },
  settings: {
    title: "Account security settings",
    text: "Manage your password and configured sign-in methods. Saving settings does not establish invitation activation or completion of required security cleanup.",
  },
} as const

export async function NativeFlowPage({
  kind,
  searchParams,
}: {
  kind: NativeAccountFlowKind
  searchParams: Promise<Record<string, string | string[] | undefined>>
}) {
  const view = await loadAccountFlow(
    kind,
    process.env,
    (await searchParams).flow,
    (await headers()).get("cookie") ?? ""
  )
  if (view.kind === "start") redirect(view.redirectTo)
  const copy = descriptions[kind]
  return (
    <>
      <h1 className="text-2xl font-semibold">{copy.title}</h1>
      <p>{copy.text}</p>
      {view.kind === "ready" ? (
        <KratosFlowForm
          ui={view.ui}
          flowId={view.flowId}
          flowKind={kind}
          publicOrigin={view.publicOrigin}
          completionMessages={view.completionMessages}
          verificationState={view.verificationState}
        />
      ) : (
        <Stopped message={view.message} />
      )}
      <nav aria-label="Account tasks" className="flex flex-wrap gap-4">
        <Link href="/" prefetch={false}>
          Account
        </Link>
        <Link href="/login" prefetch={false}>
          Sign in
        </Link>
        {kind !== "recovery" && (
          <Link href="/recovery" prefetch={false}>
            Recover account
          </Link>
        )}
      </nav>
    </>
  )
}
