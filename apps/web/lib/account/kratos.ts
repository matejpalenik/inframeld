import { Configuration, FrontendApi, ResponseError } from "@ory/client-fetch"
import type {
  LoginFlow,
  RecoveryFlow,
  RegistrationFlow,
  SettingsFlow,
  UiText,
  VerificationFlow,
} from "@ory/client-fetch"
import { checkedProviderUrl, singleParameter } from "./config"
import type { AccountConfig } from "./config"

export type AccountFlowKind =
  "login" | "registration" | "verification" | "recovery" | "settings"

export type SettingsFlowRead = {
  flow: SettingsFlow
  completionMessages: readonly UiText[]
}

export async function readCurrentIdentity(
  config: Pick<AccountConfig, "kratosInternalUrl">,
  cookie: string | undefined,
  transport: typeof globalThis.fetch = globalThis.fetch,
  signal?: AbortSignal
): Promise<string | null> {
  signal?.throwIfAborted()
  try {
    const current = await frontend(config, transport).toSession(
      { cookie },
      { signal, credentials: "same-origin" }
    )
    signal?.throwIfAborted()
    const id = current.identity?.id
    if (
      current.active !== true ||
      current.identity?.state !== "active" ||
      typeof id !== "string" ||
      !/^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i.test(id)
    )
      throw new Error("The current browser identity could not be verified.")
    return id
  } catch (error) {
    signal?.throwIfAborted()
    if (error instanceof ResponseError && error.response.status === 401)
      return null
    throw error
  }
}

export async function readRegistrationFlow(
  config: AccountConfig,
  id: string,
  cookie: string,
  transport: typeof globalThis.fetch = globalThis.fetch
): Promise<RegistrationFlow> {
  return checkedBrowserFlow(
    await frontend(config, transport).getRegistrationFlow({ id, cookie }),
    id
  )
}

export async function readVerificationFlow(
  config: AccountConfig,
  id: string,
  cookie: string,
  transport: typeof globalThis.fetch = globalThis.fetch
): Promise<VerificationFlow> {
  return checkedBrowserFlow(
    await frontend(config, transport).getVerificationFlow({ id, cookie }),
    id
  )
}

export async function readRecoveryFlow(
  config: AccountConfig,
  id: string,
  cookie: string,
  transport: typeof globalThis.fetch = globalThis.fetch
): Promise<RecoveryFlow> {
  return checkedBrowserFlow(
    await frontend(config, transport).getRecoveryFlow({ id, cookie }),
    id
  )
}

export async function readSettingsFlow(
  config: AccountConfig,
  id: string,
  cookie: string,
  transport: typeof globalThis.fetch = globalThis.fetch
): Promise<SettingsFlowRead> {
  const signal = AbortSignal.timeout(8_000)
  const api = frontend(config, transport)
  const original = checkedBrowserFlow(
    await api.getSettingsFlow({ id, cookie }, { signal }),
    id
  )
  signal.throwIfAborted()
  const target = settingsActionId(config, original)
  if (target === original.id) return { flow: original, completionMessages: [] }

  const identity = original.identity?.id
  if (
    original.state !== "success" ||
    typeof identity !== "string" ||
    singleParameter(identity, "flow") !== identity
  )
    throw new Error("The settings continuation could not be verified.")

  const flow = checkedBrowserFlow(
    await api.getSettingsFlow({ id: target, cookie }, { signal }),
    target
  )
  signal.throwIfAborted()
  if (
    flow.identity?.id !== identity ||
    settingsActionId(config, flow) !== target
  )
    throw new Error("The settings continuation could not be verified.")
  return {
    flow,
    completionMessages: (original.ui.messages ?? []).map(
      ({ id, text, type }) => ({ id, text, type })
    ),
  }
}

function settingsActionId(config: AccountConfig, flow: SettingsFlow): string {
  const action = checkedProviderUrl(
    flow.ui.action,
    config.publicOrigin,
    "/self-service/settings"
  )
  const query = new URL(action).searchParams
  const target = singleParameter(query.get("flow") ?? undefined, "flow")
  if (
    flow.ui.method.toLowerCase() !== "post" ||
    query.getAll("flow").length !== 1 ||
    [...query.keys()].some((key) => key !== "flow") ||
    target === undefined
  )
    throw new Error("The settings action could not be verified.")
  return target
}

function checkedBrowserFlow<T extends { id: string; type: string }>(
  flow: T,
  id: string
): T {
  if (flow.type !== "browser" || flow.id !== id)
    throw new Error("The browser flow could not be verified.")
  return flow
}

function frontend(
  config: Pick<AccountConfig, "kratosInternalUrl">,
  transport: typeof globalThis.fetch
): FrontendApi {
  return new FrontendApi(
    new Configuration({
      basePath: config.kratosInternalUrl,
      fetchApi: async (input, init) => {
        const signal = AbortSignal.any([
          AbortSignal.timeout(8_000),
          ...(init?.signal ? [init.signal] : []),
        ])
        const response = await transport(input, {
          ...init,
          cache: "no-store",
          redirect: "manual",
          signal,
        })
        if (response.status >= 300 && response.status < 400)
          throw new Error("Provider redirect refused.")
        const reader = response.body?.getReader()
        const chunks: Uint8Array[] = []
        let size = 0
        try {
          while (reader) {
            const next = await reader.read()
            if (next.done) break
            size += next.value.byteLength
            if (size > 65_536)
              throw new Error("Provider response exceeds the supported bound.")
            chunks.push(next.value)
          }
        } finally {
          await reader?.cancel()
        }
        const body = new Uint8Array(size)
        let offset = 0
        for (const chunk of chunks) {
          body.set(chunk, offset)
          offset += chunk.byteLength
        }
        return new Response(body, {
          status: response.status,
          statusText: response.statusText,
          headers: response.headers,
        })
      },
    })
  )
}

export async function readLoginFlow(
  config: AccountConfig,
  id: string,
  cookie: string,
  transport: typeof globalThis.fetch = globalThis.fetch
): Promise<LoginFlow> {
  const flow = await frontend(config, transport).getLoginFlow({ id, cookie })
  if (flow.type !== "browser" || flow.id !== id)
    throw new Error("The browser flow could not be verified.")
  return flow
}

export async function browserLogoutUrl(
  config: AccountConfig,
  cookie: string,
  transport: typeof globalThis.fetch = globalThis.fetch
): Promise<string> {
  const result = await frontend(config, transport).createBrowserLogoutFlow({
    cookie,
    returnTo: `${config.publicOrigin}/`,
  })
  const target = checkedProviderUrl(
    result.logout_url,
    config.publicOrigin,
    "/self-service/logout"
  )
  const query = new URL(target).searchParams
  if (query.getAll("token").length !== 1 || !query.get("token"))
    throw new Error("The browser sign-out could not be verified.")
  return target
}
