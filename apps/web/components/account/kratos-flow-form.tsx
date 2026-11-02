import { instanceOfUiNodeInputAttributes } from "@ory/client-fetch"
import type {
  UiContainer,
  UiNode,
  UiNodeInputAttributes,
  UiText,
} from "@ory/client-fetch"
import { checkedProviderUrl } from "../../lib/account/config"

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
const supportedGroups = new Set(["default", "password", "code"])
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

function Messages({ messages, id }: { messages?: UiText[]; id?: string }) {
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
}: {
  ui: UiContainer
  publicOrigin: string
  flowId: string
}) {
  let action: string
  try {
    action = checkedProviderUrl(ui.action, publicOrigin, "/self-service/login")
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
      <p role="alert">
        This sign-in form could not be verified. Restart sign-in from the
        requesting client.
      </p>
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
        .filter((group) => group === "password" || group === "code")
    ),
  ]
  if (
    inputs.some((input) => input === undefined) ||
    csrf.length !== 1 ||
    !methods.length
  ) {
    return (
      <p role="alert">
        This sign-in interaction is not supported by this account page. Return
        to the requesting client. Required factors have not been skipped.
      </p>
    )
  }
  return (
    <div className="space-y-6">
      <Messages messages={ui.messages} />
      {methods.map((method) => (
        <section
          key={method}
          className="space-y-3"
          aria-labelledby={`method-${method}`}
        >
          <h2 id={`method-${method}`} className="font-semibold">
            {method === "password" ? "Use your password" : "Use an email code"}
          </h2>
          <form action={action} method="post" className="space-y-4">
            {ui.nodes.map((node, index) => {
              if (node.group !== "default" && node.group !== method) return null
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
                    formNoValidate={input.name === "resend"}
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
                        ? "current-password"
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
