"use client"

import type { AccountView } from "../../lib/account/session"
import { inspectAccount } from "../../lib/account/session"
import { useCallback, useEffect, useRef, useState } from "react"

function AccountSummary({ view }: { view: AccountView }) {
  if (view.kind === "signed-out")
    return (
      <p role="status">
        No verified browser session is available. Sign in to continue. Sign-in
        alone does not grant installation access.
      </p>
    )
  if (view.kind === "unavailable")
    return (
      <p role="alert">
        Your browser identity could not be checked. No account access is
        confirmed.
      </p>
    )
  if (view.kind === "changed")
    return (
      <p role="alert">
        Your browser identity changed during the check. Check your current
        account again.
      </p>
    )
  return (
    <div className="space-y-4">
      <dl className="space-y-2 break-words">
        <div>
          <dt>Signed-in identity</dt>
          <dd className="font-mono text-sm">{view.identityId}</dd>
        </div>
        {view.access.kind === "admitted" && (
          <div>
            <dt>Local Inframeld account</dt>
            <dd className="font-mono text-sm">{view.access.principalId}</dd>
          </div>
        )}
      </dl>
      <p role="status">
        {view.access.kind === "admitted"
          ? "Your local Inframeld account is admitted. Every action still checks current permissions."
          : view.access.kind === "denied"
            ? "Your browser identity is verified. Inframeld access is not available. It may require admission or be restricted. This page cannot determine or clear the reason."
            : "Your browser identity is verified, but Inframeld access could not be checked. No admission or action permission is confirmed."}
      </p>
    </div>
  )
}

export function AccountState({
  initialView,
  publicOrigin,
}: {
  initialView: AccountView
  publicOrigin: string
}) {
  const [view, setView] = useState<AccountView | { kind: "checking" }>(
    initialView
  )
  const active = useRef<AbortController | null>(null)
  const details = useRef<HTMLDivElement>(null)

  const hide = useCallback(() => {
    if (details.current) details.current.hidden = true
    active.current?.abort()
    setView({ kind: "checking" })
  }, [])
  const recheck = useCallback(async () => {
    if (document.visibilityState === "hidden") return
    hide()
    const controller = new AbortController()
    active.current = controller
    try {
      const current = await inspectAccount({
        baseUrl: publicOrigin,
        kratosUrl: publicOrigin,
        signal: controller.signal,
      })
      if (!controller.signal.aborted) setView(current)
    } catch {
      if (!controller.signal.aborted) setView({ kind: "unavailable" })
    }
  }, [hide, publicOrigin])

  useEffect(() => {
    const restored = (event: PageTransitionEvent) => {
      if (event.persisted) void recheck()
    }
    const visibility = () => {
      if (document.visibilityState === "hidden") hide()
      else void recheck()
    }
    window.addEventListener("blur", hide)
    window.addEventListener("pagehide", hide)
    window.addEventListener("focus", recheck)
    window.addEventListener("pageshow", restored)
    document.addEventListener("visibilitychange", visibility)
    return () => {
      active.current?.abort()
      window.removeEventListener("blur", hide)
      window.removeEventListener("pagehide", hide)
      window.removeEventListener("focus", recheck)
      window.removeEventListener("pageshow", restored)
      document.removeEventListener("visibilitychange", visibility)
    }
  }, [hide, recheck])

  useEffect(() => {
    if (details.current) {
      details.current.hidden = false
      if (view.kind === "unavailable" || view.kind === "changed")
        details.current.focus()
    }
  }, [view])

  return (
    <section
      aria-label="Current account"
      className="space-y-4 rounded-lg border p-4"
    >
      <p className="text-sm break-words">Installation: {publicOrigin}</p>
      {view.kind === "checking" ? (
        <p role="status">Checking your current browser account…</p>
      ) : (
        <div ref={details} tabIndex={-1}>
          <AccountSummary view={view} />
        </div>
      )}
      <button
        type="button"
        onClick={() => void recheck()}
        disabled={view.kind === "checking"}
        className="min-h-11 rounded-md border px-4 py-2 disabled:opacity-50"
      >
        Check account again
      </button>
    </section>
  )
}
