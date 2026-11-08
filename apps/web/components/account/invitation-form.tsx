"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import type {
  InvitationActivationResponse,
  InvitationAssignmentRequest,
} from "@inframeld/sdk"
import {
  activateOriginalInvitation,
  currentInvitationIdentity,
  inspectInvitation,
  invitationOriginal,
} from "../../lib/account/invitations"
import type {
  InvitationOriginal,
  InvitationPreview,
} from "../../lib/account/invitations"

const unknownOutcome =
  "The activation outcome is unknown. Cancellation does not prove rollback. Preserve the exact original token and key, then explicitly recover under the same identity."
const buttonClass = "min-h-11 rounded-md border px-4 py-2 disabled:opacity-50"

function Assignment({
  assignment,
}: {
  assignment: InvitationAssignmentRequest
}) {
  switch (assignment.kind) {
    case "admission-only":
      return (
        <>
          Local account admission only{" "}
          <span className="text-sm">(admission-only)</span>
        </>
      )
    case "project-membership":
      return <>Project membership: {assignment.projectId}</>
    case "group-membership":
      return (
        <>
          Group membership: {assignment.accessGroupId} in Project{" "}
          {assignment.projectId}
        </>
      )
    case "group-manager":
      return (
        <>
          Group management and membership: {assignment.accessGroupId} in Project{" "}
          {assignment.projectId}. This does not add Project membership.
        </>
      )
    case "action-grant":
      return (
        <>
          {assignment.canGrant ? "Use and grant" : "Use"} {assignment.actionId}{" "}
          on {JSON.stringify(assignment.target)}
        </>
      )
  }
}

export function InvitationForm({ publicOrigin }: { publicOrigin: string }) {
  const [token, setToken] = useState("")
  const [key, setKey] = useState("")
  const [originalIdentity, setOriginalIdentity] = useState("")
  const [saved, setSaved] = useState(false)
  const [identity, setIdentity] = useState<string | null>(null)
  const [preview, setPreview] = useState<Extract<
    InvitationPreview,
    { kind: "ready" }
  > | null>(null)
  const [receipt, setReceipt] = useState<InvitationActivationResponse | null>(
    null
  )
  const [notice, setNotice] = useState(
    "Preview a new invitation, or explicitly recover your saved original activation."
  )
  const [busy, setBusy] = useState(false)
  const [hidden, setHidden] = useState(false)
  const [hasOriginal, setHasOriginal] = useState(false)
  const original = useRef<InvitationOriginal | null>(null)
  const uncertainOriginal = useRef(false)
  const lastIdentity = useRef<string | null>(null)
  const details = useRef<HTMLDivElement>(null)
  const status = useRef<HTMLParagraphElement>(null)
  const active = useRef<{ controller: AbortController; write: boolean } | null>(
    null
  )
  const generation = useRef(0)

  const stopWaiting = useCallback(() => {
    generation.current++
    active.current?.controller.abort()
    active.current = null
  }, [])

  const discard = useCallback(() => {
    original.current = null
    uncertainOriginal.current = false
    setHasOriginal(false)
    setToken("")
    setKey("")
    setOriginalIdentity("")
    setSaved(false)
    setPreview(null)
    setReceipt(null)
  }, [])

  const hide = useCallback(() => {
    if (details.current) details.current.hidden = true
    if (active.current?.write && original.current) {
      uncertainOriginal.current = true
      setNotice(unknownOutcome)
    }
    stopWaiting()
    setBusy(false)
    setHidden(true)
    setIdentity(null)
    setPreview(null)
    setReceipt(null)
  }, [stopWaiting])

  const recheck = useCallback(async () => {
    if (document.visibilityState === "hidden") return
    hide()
    const controller = new AbortController()
    const version = generation.current
    active.current = { controller, write: false }
    setBusy(true)
    try {
      const current = await currentInvitationIdentity({
        publicOrigin,
        signal: controller.signal,
      })
      if (version !== generation.current) return
      const previous = original.current?.identityId ?? lastIdentity.current
      if (previous && current !== previous) {
        discard()
        setNotice(
          "Your browser identity changed. Protected context was discarded. Restore an original request only under its original identity, then make a fresh explicit decision."
        )
      } else {
        setNotice(
          uncertainOriginal.current
            ? unknownOutcome
            : current
              ? "Current identity verified. Choose an explicit next action. No activation was sent."
              : "Sign in with your browser identity before continuing."
        )
      }
      lastIdentity.current = current
      setIdentity(current)
      setHidden(false)
    } catch {
      if (version === generation.current)
        setNotice(
          uncertainOriginal.current
            ? `${unknownOutcome} Your current identity could not be checked. Protected context remains hidden.`
            : "Your browser identity could not be checked. Protected context remains hidden. This check sent no activation."
        )
    } finally {
      if (version === generation.current) {
        active.current = null
        setBusy(false)
      }
    }
  }, [discard, hide, publicOrigin])

  useEffect(() => {
    const restored = (event: PageTransitionEvent) => {
      if (event.persisted) void recheck()
    }
    const visible = () => {
      if (document.visibilityState === "hidden") hide()
      else void recheck()
    }
    window.addEventListener("blur", hide)
    window.addEventListener("pagehide", hide)
    window.addEventListener("focus", recheck)
    window.addEventListener("pageshow", restored)
    document.addEventListener("visibilitychange", visible)
    return () => {
      stopWaiting()
      window.removeEventListener("blur", hide)
      window.removeEventListener("pagehide", hide)
      window.removeEventListener("focus", recheck)
      window.removeEventListener("pageshow", restored)
      document.removeEventListener("visibilitychange", visible)
    }
  }, [hide, recheck, stopWaiting])

  async function run(mode: "preview" | "activate" | "recover") {
    if (active.current) return
    const controller = new AbortController()
    const signal = AbortSignal.any([
      controller.signal,
      AbortSignal.timeout(8_000),
    ])
    const version = ++generation.current
    active.current = { controller, write: mode !== "preview" }
    setBusy(true)
    setReceipt(null)
    try {
      const connection = { publicOrigin, signal }
      if (mode === "preview") {
        const result = await inspectInvitation(connection, token)
        if (version !== generation.current) return
        if (result.kind === "ready") {
          lastIdentity.current = result.identityId
          setIdentity(result.identityId)
          setOriginalIdentity(result.identityId)
          setPreview(result)
          setNotice(
            "Review every intended assignment. Preview does not grant access or guarantee later activation."
          )
        } else {
          setPreview(null)
          if (result.kind === "identity-changed") {
            discard()
            setIdentity(null)
            setNotice(
              "Your browser identity changed. Protected context was discarded."
            )
          } else setNotice(result.message)
        }
        return
      }
      if (!saved) throw new Error("Original context not saved")
      let request = original.current
      if (!request) {
        const current =
          mode === "activate"
            ? preview?.identityId
            : await currentInvitationIdentity(connection)
        signal.throwIfAborted()
        if (mode === "recover" && current !== originalIdentity) {
          discard()
          setIdentity(null)
          setNotice(
            "Your browser identity changed from the saved original. Protected context was discarded. Sign in as the original identity before restoring that request."
          )
          return
        }
        if (!current || (mode === "activate" && !preview))
          throw new Error("No verified decision")
        request = invitationOriginal(current, token, key)
        original.current = request
        setHasOriginal(true)
        lastIdentity.current = current
        setIdentity(current)
      }
      uncertainOriginal.current = true
      const result = await activateOriginalInvitation(connection, request)
      if (version !== generation.current) return
      setPreview(null)
      if (result.kind === "identity-changed") {
        discard()
        setIdentity(null)
        setNotice(
          "Your browser identity changed. Protected context was discarded. No result from the previous account is shown."
        )
      } else if (result.kind === "completed") {
        uncertainOriginal.current = false
        setReceipt(result.receipt)
        setNotice(
          "Activation confirmed. These are the original committed revisions, not a snapshot of current permissions."
        )
      } else {
        uncertainOriginal.current = result.kind === "uncertain"
        setNotice(result.message)
      }
    } catch {
      if (version === generation.current)
        setNotice(
          original.current
            ? unknownOutcome
            : "Check your browser identity, token and key. Save the exact original context before explicitly activating or recovering."
        )
    } finally {
      if (version === generation.current) {
        active.current = null
        setBusy(false)
        status.current?.focus()
      }
    }
  }

  function cancelWaiting() {
    const uncertain = active.current?.write && original.current
    stopWaiting()
    setBusy(false)
    setPreview(null)
    setReceipt(null)
    if (!uncertain) discard()
    else uncertainOriginal.current = true
    setNotice(
      uncertain
        ? unknownOutcome
        : "The unused decision was cancelled. No activation is confirmed."
    )
  }

  return (
    <section aria-label="Invitation activation" className="space-y-5">
      <p className="text-sm break-words">Installation: {publicOrigin}</p>
      <p ref={status} tabIndex={-1} role="status" className="break-words">
        {busy ? "Checking your explicit invitation request…" : notice}
      </p>
      {busy && (
        <button type="button" onClick={cancelWaiting} className={buttonClass}>
          Cancel waiting
        </button>
      )}
      <button
        type="button"
        onClick={() => void recheck()}
        disabled={busy}
        className={buttonClass}
      >
        Check browser identity
      </button>
      <div
        ref={details}
        hidden={hidden}
        data-protected-invitation
        className="space-y-5"
      >
        {identity && (
          <p className="break-words">
            Signed-in identity:{" "}
            <span className="font-mono text-sm">{identity}</span>
          </p>
        )}
        <p>
          Paste the protected token here, never in a URL. This page does not
          save it or the original key across reloads. Preserve your exact
          original request privately before activation.
        </p>
        <form
          autoComplete="off"
          onSubmit={(event) => {
            event.preventDefault()
            void run("preview")
          }}
          className="space-y-4"
        >
          <label className="block space-y-2">
            Protected invitation token
            <input
              aria-label="Protected invitation token"
              type="password"
              autoComplete="off"
              value={token}
              readOnly={hasOriginal}
              disabled={busy}
              maxLength={43}
              onChange={(event) => {
                setToken(event.target.value)
                setPreview(null)
                setReceipt(null)
              }}
              className="min-h-11 w-full rounded-md border px-3 py-2"
            />
          </label>
          <label className="block space-y-2">
            Original activation identity
            <input
              aria-label="Original activation identity"
              autoComplete="off"
              value={originalIdentity}
              readOnly={hasOriginal || preview !== null}
              disabled={busy}
              maxLength={36}
              onChange={(event) => setOriginalIdentity(event.target.value)}
              className="min-h-11 w-full rounded-md border px-3 py-2"
            />
          </label>
          <label className="block space-y-2">
            Original activation key
            <input
              aria-label="Original activation key"
              type="password"
              autoComplete="off"
              value={key}
              readOnly={hasOriginal}
              disabled={busy}
              maxLength={128}
              onChange={(event) => setKey(event.target.value)}
              className="min-h-11 w-full rounded-md border px-3 py-2"
            />
          </label>
          <label className="flex min-h-11 items-start gap-3">
            <input
              type="checkbox"
              checked={saved}
              disabled={busy || hasOriginal}
              onChange={(event) => setSaved(event.target.checked)}
              className="mt-1 size-5"
            />
            I saved this exact token and key privately with POST
            /v1/invitations/activate, including its original identity. Recovery
            must use that same request.
          </label>
          <button
            type="submit"
            disabled={busy || hasOriginal || !token}
            className={buttonClass}
          >
            Preview invitation
          </button>
        </form>
        {preview && (
          <section
            aria-label="Reviewed invitation"
            className="space-y-3 rounded-md border p-4"
          >
            <h2 className="text-xl font-semibold">Intended access</h2>
            <p className="break-words">
              Organization: {preview.preview.organizationId}
            </p>
            <p>
              Expires:{" "}
              <time dateTime={preview.preview.expiresAt}>
                {preview.preview.expiresAt}
              </time>
            </p>
            <ul className="list-disc space-y-2 pl-5 break-words">
              {preview.preview.assignments.map((assignment, index) => (
                <li key={index}>
                  <Assignment assignment={assignment} />
                </li>
              ))}
            </ul>
            <ul className="space-y-2 break-words">
              {preview.preview.scopes.map((scope, index) => (
                <li key={index}>
                  {scope.displayName}:{" "}
                  <span className="font-mono text-sm">
                    {JSON.stringify(scope.target)}
                  </span>
                </li>
              ))}
            </ul>
            <button
              type="button"
              disabled={busy || !saved || !key}
              onClick={() => void run("activate")}
              className={buttonClass}
            >
              Activate reviewed invitation
            </button>
          </section>
        )}
        <p>
          For an uncertain original activation, recover directly using its saved
          token, key and identity. A consumed invitation may no longer be
          previewed. Recovery never starts from a new preview.
        </p>
        <button
          type="button"
          disabled={busy || !saved || !token || !key || !originalIdentity}
          onClick={() => void run("recover")}
          className={buttonClass}
        >
          Recover original activation
        </button>
        {receipt && (
          <section
            aria-label="Original activation receipt"
            className="space-y-2 rounded-md border p-4 break-words"
          >
            <h2 className="text-xl font-semibold">
              Original activation receipt
            </h2>
            <p>Local account: {receipt.principalId}</p>
            <p>Invitation: {receipt.invitationId}</p>
            <p>Organization: {receipt.organizationId}</p>
            <p>Operation: {receipt.operationId}</p>
            <p>
              Organization Access revision: {receipt.organizationAccessRevision}
            </p>
            <ul>
              {receipt.projectAccessRevisions.map((project) => (
                <li key={project.projectId}>
                  Project {project.projectId}: Access revision{" "}
                  {project.accessRevision}
                </li>
              ))}
            </ul>
            <p>Original recovery expires: {receipt.idempotencyExpiresAt}</p>
          </section>
        )}
        <button
          type="button"
          onClick={() => {
            cancelWaiting()
            discard()
            setNotice(
              "Protected context discarded from this page. This does not cancel a dispatched activation. Keep your private original copy if its outcome is uncertain."
            )
          }}
          className={buttonClass}
        >
          Discard protected context
        </button>
      </div>
    </section>
  )
}
