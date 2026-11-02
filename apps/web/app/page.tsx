import Link from "next/link"
import { accountConfig } from "../lib/account/config"

export const dynamic = "force-dynamic"

export default function Page() {
  let configured = false
  try {
    accountConfig(process.env)
    configured = true
  } catch {}
  return (
    <main className="mx-auto flex min-h-svh max-w-lg flex-col justify-center gap-6 px-5 py-12">
      <p className="text-sm font-medium text-muted-foreground">
        Inframeld account
      </p>
      <h1 className="text-3xl font-semibold tracking-tight">
        A place to sign in.
      </h1>
      <p>
        Use an existing account to continue a request from the Inframeld CLI.
        The CLI confirms the result after you return to it.
      </p>
      {configured ? (
        <nav aria-label="Account" className="flex flex-wrap gap-3">
          <Link
            href="/login"
            prefetch={false}
            className="inline-flex min-h-11 items-center rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground"
          >
            Sign in
          </Link>
          <Link
            href="/logout"
            prefetch={false}
            className="inline-flex min-h-11 items-center rounded-md border px-4 py-2"
          >
            Sign out of browser
          </Link>
        </nav>
      ) : (
        <p role="status">
          The account HTTPS profile is not configured. The default HTTP
          development app does not support CLI sign-in.
        </p>
      )}
      <p className="text-sm text-muted-foreground">
        Account creation, recovery and account management are not available
        here.
      </p>
    </main>
  )
}
