"use client"

import { useEffect, useRef, useState } from "react"
import { decideConsent, inspectConsent } from "../../../lib/account/consent"
import type { ConsentView } from "../../../lib/account/consent"

export function ConsentForm({
  initialView,
  challenge,
  publicOrigin,
  hydraOrigin,
}: {
  initialView: ConsentView
  challenge: string
  publicOrigin: string
  hydraOrigin: string
}) {
  const [view, setView] = useState<ConsentView | { kind: "checking" }>(
    initialView
  )
  const [remember, setRemember] = useState(false)
  const [pending, setPending] = useState(false)
  const attempted = useRef(false)
  const active = useRef<AbortController | null>(null)
  const summary = useRef<HTMLParagraphElement>(null)
  const details = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const hide = () => {
      if (details.current) details.current.hidden = true
      if (!attempted.current) {
        active.current?.abort()
        setView({ kind: "checking" })
      }
    }
    const recheck = async () => {
      if (attempted.current || document.visibilityState === "hidden") return
      hide()
      active.current?.abort()
      const controller = new AbortController()
      active.current = controller
      const checked = await inspectConsent({
        baseUrl: publicOrigin,
        challenge,
        signal: controller.signal,
      })
      if (!controller.signal.aborted) setView(checked)
    }
    const restored = (event: PageTransitionEvent) => {
      if (event.persisted) void recheck()
    }
    const visibility = () => {
      if (document.visibilityState === "hidden") hide()
      else void recheck()
    }
    window.addEventListener("pagehide", hide)
    window.addEventListener("blur", hide)
    window.addEventListener("focus", recheck)
    window.addEventListener("pageshow", restored)
    document.addEventListener("visibilitychange", visibility)
    return () => {
      active.current?.abort()
      window.removeEventListener("pagehide", hide)
      window.removeEventListener("blur", hide)
      window.removeEventListener("focus", recheck)
      window.removeEventListener("pageshow", restored)
      document.removeEventListener("visibilitychange", visibility)
    }
  }, [challenge, publicOrigin])

  useEffect(() => {
    if (view.kind === "stopped") summary.current?.focus()
    if (view.kind === "ready" && details.current) details.current.hidden = false
  }, [view])

  async function decide(decision: "allow" | "deny") {
    if (attempted.current || view.kind !== "ready") return
    attempted.current = true
    setPending(true)
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    const result = await decideConsent(
      { baseUrl: publicOrigin, challenge, signal: controller.signal },
      decision,
      remember,
      hydraOrigin
    )
    if (controller.signal.aborted) return
    if (result.kind === "continue") window.location.assign(result.redirectTo)
    else {
      setView({ kind: "stopped", message: result.message })
      setPending(false)
    }
  }

  if (view.kind === "checking")
    return <p role="status">Checking your current browser session…</p>
  if (view.kind === "stopped")
    return (
      <p ref={summary} role="alert" tabIndex={-1}>
        {view.message}
      </p>
    )
  return (
    <>
      {pending && (
        <p role="status">Sending your decision. Do not submit it again.</p>
      )}
      <div ref={details} className="space-y-6">
        <p>
          The requesting CLI will use the account and installation below.
          Confirm both before continuing.
        </p>
        <dl className="space-y-3 rounded-lg border p-4 break-words">
          <div>
            <dt className="text-sm text-muted-foreground">Account subject</dt>
            <dd className="font-mono text-sm">{view.details.accountSubject}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Installation</dt>
            <dd>{view.details.installation}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Client</dt>
            <dd>{view.details.clientId}</dd>
          </div>
          <div>
            <dt className="text-sm text-muted-foreground">Requested scopes</dt>
            <dd>{view.details.requestedScopes.join(", ")}</dd>
          </div>
        </dl>
        <form
          onSubmit={(event) => {
            event.preventDefault()
            const submitter = (event.nativeEvent as SubmitEvent).submitter
            if (
              submitter instanceof HTMLButtonElement &&
              (submitter.value === "allow" || submitter.value === "deny")
            )
              void decide(submitter.value)
          }}
          className="space-y-5"
          aria-busy={pending}
        >
          {view.details.approvalRequired && (
            <label className="flex items-start gap-3">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.target.checked)}
                disabled={pending}
                className="mt-1 size-5"
              />
              <span>
                Remember this approval for {view.details.rememberConsentSeconds}{" "}
                seconds on this installation.
              </span>
            </label>
          )}
          {!view.details.approvalRequired && (
            <p>
              This account already approved the requested access. Continue to
              the requesting client.
            </p>
          )}
          <div className="flex flex-wrap gap-3">
            <button
              type="submit"
              value="allow"
              disabled={pending}
              className="min-h-11 rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
            >
              {view.details.approvalRequired
                ? "Allow CLI access"
                : "Continue to CLI"}
            </button>
            <button
              type="submit"
              value="deny"
              disabled={pending}
              className="min-h-11 rounded-md border px-4 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </form>
        <p className="text-sm text-muted-foreground">
          This page does not receive or display CLI tokens. Complete sign-in in
          the requesting client.
        </p>
      </div>
    </>
  )
}
