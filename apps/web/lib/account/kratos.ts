import { Configuration, FrontendApi } from "@ory/client-fetch"
import type { LoginFlow } from "@ory/client-fetch"
import { checkedProviderUrl } from "./config"
import type { AccountConfig } from "./config"

function frontend(
  config: AccountConfig,
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
