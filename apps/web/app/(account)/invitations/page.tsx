import Link from "next/link"
import { InvitationForm } from "../../../components/account/invitation-form"
import { accountConfig } from "../../../lib/account/config"

export const dynamic = "force-dynamic"

export default function InvitationsPage() {
  let origin: string | undefined
  try {
    origin = accountConfig(process.env).publicOrigin
  } catch {}
  return (
    <main className="mx-auto min-h-svh max-w-xl space-y-6 px-5 py-12">
      <h1 className="text-3xl font-semibold tracking-tight">
        Use an invitation
      </h1>
      <p>
        Review intended access under your current browser identity. Identity
        registration, password setup and Inframeld admission are separate steps.
      </p>
      {origin ? (
        <InvitationForm publicOrigin={origin} />
      ) : (
        <p role="alert">
          The account HTTPS profile is not configured. No invitation can be
          checked.
        </p>
      )}
      <nav aria-label="Account tasks" className="flex flex-wrap gap-4">
        <Link href="/" prefetch={false}>
          Current account
        </Link>
        <Link href="/login" prefetch={false}>
          Sign in
        </Link>
        <Link href="/settings" prefetch={false}>
          Password and security settings
        </Link>
      </nav>
    </main>
  )
}
