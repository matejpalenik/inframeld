import {
  instanceOfUiNodeImageAttributes,
  instanceOfUiNodeInputAttributes,
  instanceOfUiNodeTextAttributes,
} from "@ory/client-fetch"
import type {
  UiContainer,
  UiNode,
  UiNodeInputAttributes,
  UiText,
} from "@ory/client-fetch"
import { checkedProviderUrl } from "../../lib/account/config"
import type { AccountFlowKind } from "../../lib/account/kratos"

const supportedTypes = new Set([
  "text",
  "password",
  "email",
  "number",
  "tel",
  "hidden",
  "submit",
  "checkbox",
])
const supportedGroups = new Set([
  "default",
  "password",
  "code",
  "profile",
  "totp",
  "lookup_secret",
  "oidc",
])
const fieldClass =
  "w-full rounded-md border bg-background px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
const buttonClass =
  "min-h-11 rounded-md border px-4 py-2 font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"

function attributes(node: UiNode): UiNodeInputAttributes | undefined {
  const input = node.attributes
  if (
    node.type !== "input" ||
    !supportedGroups.has(node.group) ||
    !instanceOfUiNodeInputAttributes(input) ||
    !supportedTypes.has(input.type) ||
    typeof input.name !== "string" ||
    !input.name ||
    input.onclick !== undefined ||
    input.onload !== undefined ||
    input.onclickTrigger !== undefined ||
    input.onloadTrigger !== undefined ||
    input.options !== undefined ||
    (input.value !== undefined &&
      input.value !== null &&
      typeof input.value !== "string" &&
      typeof input.value !== "number" &&
      !(input.type === "checkbox" && typeof input.value === "boolean"))
  )
    return undefined
  return input
}

function supportedNode(node: UiNode, flowKind: AccountFlowKind): boolean {
  if (!supportedGroups.has(node.group)) return false
  if (node.type === "input") return attributes(node) !== undefined
  const value = node.attributes
  if (
    node.type === "text" &&
    instanceOfUiNodeTextAttributes(value) &&
    value.node_type === "text"
  )
    return typeof value.text.text === "string"
  // Native enrollment images stay inside the checked flow, never on a remote host.
  return (
    flowKind === "settings" &&
    node.group === "totp" &&
    node.type === "img" &&
    instanceOfUiNodeImageAttributes(value) &&
    value.node_type === "img" &&
    /^data:image\/png;base64,[A-Za-z0-9+/]+={0,2}$/.test(value.src) &&
    value.src.length <= 65_536 &&
    Number.isInteger(value.width) &&
    value.width > 0 &&
    value.width <= 1024 &&
    Number.isInteger(value.height) &&
    value.height > 0 &&
    value.height <= 1024 &&
    Boolean(node.meta.label?.text)
  )
}

function Messages({
  messages,
  id,
}: {
  messages?: readonly UiText[]
  id?: string
}) {
  if (!messages?.length) return null
  return (
    <div
      id={id}
      className="space-y-2"
      role={
        messages.some((message) => message.type === "error")
          ? "alert"
          : "status"
      }
    >
      {messages.map((message, index) => (
        <p key={`${message.id}-${index}`}>{message.text}</p>
      ))}
    </div>
  )
}

export function KratosFlowForm({
  ui,
  publicOrigin,
  flowId,
  flowKind = "login",
  completionMessages,
}: {
  ui: UiContainer
  publicOrigin: string
  flowId: string
  flowKind?: AccountFlowKind
  completionMessages?: readonly UiText[]
}) {
  let action: string
  try {
    action = checkedProviderUrl(
      ui.action,
      publicOrigin,
      `/self-service/${flowKind}`
    )
    const query = new URL(action).searchParams
    if (
      ui.method.toLowerCase() !== "post" ||
      query.getAll("flow").length !== 1 ||
      query.get("flow") !== flowId ||
      [...query.keys()].some((key) => key !== "flow")
    )
      throw new Error()
  } catch {
    return (
      <>
        <Messages messages={completionMessages} />
        <p role="alert">
          This account form could not be verified. Restart this account
          operation.
        </p>
      </>
    )
  }
  const inputs = ui.nodes.map(attributes)
  const csrf = inputs.filter(
    (input) =>
      input?.name === "csrf_token" &&
      input.type === "hidden" &&
      typeof input.value === "string" &&
      input.value.length > 0
  )
  const methods = [
    ...new Set(
      ui.nodes
        .map((node) => node.group)
        .filter((group) => supportedGroups.has(group) && group !== "default")
    ),
  ]
  if (
    ui.nodes.some((node) => !supportedNode(node, flowKind)) ||
    csrf.length !== 1 ||
    !methods.length
  ) {
    return (
      <>
        <Messages messages={completionMessages} />
        <p role="alert">
          This interaction is not supported by this account page. Required
          factors have not been skipped. Return to the account task that started
          it.
        </p>
      </>
    )
  }
  return (
    <div className="space-y-6">
      <Messages messages={completionMessages} />
      <Messages messages={ui.messages} />
      {methods.map((method) => (
        <section
          key={method}
          className="space-y-3"
          aria-labelledby={`method-${method}`}
        >
          <h2 id={`method-${method}`} className="font-semibold">
            {method === "password"
              ? flowKind === "login"
                ? "Use your password"
                : "Set your password"
              : method === "code"
                ? "Use an email code"
                : method === "totp"
                  ? "Authenticator app"
                  : method === "lookup_secret"
                    ? "Backup recovery codes"
                    : method === "oidc"
                      ? "Company sign-in"
                      : "Account details"}
          </h2>
          <form action={action} method="post" className="space-y-4">
            {ui.nodes.map((node, index) => {
              if (node.group !== "default" && node.group !== method) return null
              if (
                node.type === "text" &&
                instanceOfUiNodeTextAttributes(node.attributes)
              )
                return (
                  <div key={index} className="space-y-2 break-words">
                    {node.meta.label && <p>{node.meta.label.text}</p>}
                    <p>{node.attributes.text.text}</p>
                    <Messages messages={node.messages} />
                  </div>
                )
              if (
                node.type === "img" &&
                instanceOfUiNodeImageAttributes(node.attributes)
              )
                return (
                  <div key={index} className="space-y-2">
                    {/* The native provider supplies an in-memory QR image. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={node.attributes.src}
                      alt={node.meta.label!.text}
                      width={node.attributes.width}
                      height={node.attributes.height}
                      loading="lazy"
                    />
                    <Messages messages={node.messages} />
                  </div>
                )
              const input = inputs[index]!
              const value =
                typeof input.value === "string" ||
                typeof input.value === "number"
                  ? input.value
                  : undefined
              const id = `kratos-${method}-${index}`
              const label =
                node.meta.label?.text ?? input.label?.text ?? input.name
              if (input.type === "hidden")
                return (
                  <input
                    key={index}
                    type="hidden"
                    name={input.name}
                    value={value ?? ""}
                    disabled={input.disabled}
                  />
                )
              if (input.type === "submit")
                return (
                  <button
                    key={index}
                    className={buttonClass}
                    type="submit"
                    formNoValidate={
                      input.name === "resend" ||
                      ((flowKind === "login" || flowKind === "registration") &&
                        node.group === "oidc" &&
                        input.name === "provider" &&
                        typeof input.value === "string" &&
                        input.value.length > 0)
                    }
                    name={input.name}
                    value={value ?? ""}
                    disabled={input.disabled}
                  >
                    {label}
                  </button>
                )
              return (
                <div key={index} className="space-y-2">
                  <label htmlFor={id} className="block font-medium">
                    {label}
                  </label>
                  <input
                    id={id}
                    name={input.name}
                    type={input.type}
                    defaultValue={
                      input.type === "password" || input.type === "checkbox"
                        ? undefined
                        : value
                    }
                    defaultChecked={
                      input.type === "checkbox"
                        ? input.value === true
                        : undefined
                    }
                    required={input.required}
                    disabled={input.disabled}
                    maxLength={input.maxlength}
                    pattern={input.pattern}
                    autoComplete={
                      input.autocomplete ??
                      (input.type === "password"
                        ? flowKind === "login"
                          ? "current-password"
                          : "new-password"
                        : input.name === "code"
                          ? "one-time-code"
                          : input.name === "identifier"
                            ? "username"
                            : undefined)
                    }
                    aria-invalid={
                      node.messages.some(
                        (message) => message.type === "error"
                      ) || undefined
                    }
                    aria-describedby={
                      node.messages.length ? `${id}-messages` : undefined
                    }
                    className={fieldClass}
                  />
                  <Messages id={`${id}-messages`} messages={node.messages} />
                </div>
              )
            })}
          </form>
        </section>
      ))}
    </div>
  )
}
