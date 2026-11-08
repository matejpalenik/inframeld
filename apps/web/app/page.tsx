import Link from "next/link"
import { accountConfig } from "../lib/account/config"
import { headers } from "next/headers"
import { AccountState } from "../components/account/account-state"
import { inspectAccount } from "../lib/account/session"
import type { AccountView } from "../lib/account/session"

export const dynamic = "force-dynamic"

export default async function Page() {
  let config
  let view: AccountView = { kind: "unavailable" }
  try {
    config = accountConfig(process.env)
    view = await inspectAccount({
      baseUrl: config.apiInternalUrl,
      kratosUrl: config.kratosInternalUrl,
      cookie: (await headers()).get("cookie") ?? "",
    })
  } catch {}
  return (
    <main className="mx-auto flex min-h-svh max-w-lg flex-col justify-center gap-6 px-5 py-12">
      <p className="text-sm font-medium text-muted-foreground">
        Inframeld account
      </p>
      <h1 className="text-3xl font-semibold tracking-tight">
        Your Inframeld account
      </h1>
      <p>
        Manage your browser identity and account security here. Identity
        verification and permission to use Inframeld are separate checks. The
        CLI confirms its own result after you return to it.
      </p>
      {config ? (
        <>
          <AccountState initialView={view} publicOrigin={config.publicOrigin} />
          <nav aria-label="Account tasks" className="flex flex-wrap gap-3">
            <Link
              href="/login"
              prefetch={false}
              className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground"
            >
              Sign in
            </Link>
            <Link
              href="/registration"
              prefetch={false}
              className="inline-flex min-h-11 items-center rounded-md border px-4 py-2"
            >
              Create identity
            </Link>
            <Link
              href="/verification"
              prefetch={false}
              className="inline-flex min-h-11 items-center rounded-md border px-4 py-2"
            >
              Verify email
            </Link>
            <Link
              href="/settings"
              prefetch={false}
              className="inline-flex min-h-11 items-center rounded-md border px-4 py-2"
            >
              Security settings
            </Link>
            <Link
              href="/recovery"
              prefetch={false}
              className="inline-flex min-h-11 items-center rounded-md border px-4 py-2"
            >
              Recover account
            </Link>
            <Link
              href="/invitations"
              prefetch={false}
              className="inline-flex min-h-11 items-center rounded-md border px-4 py-2"
            >
              Use an invitation
            </Link>
            <Link
              href="/logout"
              prefetch={false}
              className="inline-flex min-h-11 items-center rounded-md border px-4 py-2"
            >
              Sign out of browser
            </Link>
          </nav>
        </>
      ) : (
        <p role="status">
          The account HTTPS profile is not configured. The default HTTP
          development app does not support CLI sign-in.
        </p>
      )}
      <p className="text-sm text-muted-foreground">
        Signing in does not claim host authority, create starter resources or
        restore removed permissions.
      </p>
    </main>
  )
}
