import type { UiContainer, UiText } from "@ory/client-fetch"
import type { AccountFlowKind } from "./kratos"
import {
  readRecoveryFlow,
  readRegistrationFlow,
  readSettingsFlow,
  readVerificationFlow,
} from "./kratos"
import { accountConfig, singleParameter } from "./config"

export type NativeAccountFlowKind = Exclude<AccountFlowKind, "login">

export type NativeAccountFlowView =
  | { kind: "start"; redirectTo: string }
  | {
      kind: "ready"
      ui: UiContainer
      flowId: string
      publicOrigin: string
      completionMessages?: readonly UiText[]
      verificationState?: "passed_challenge"
    }
  | { kind: "stopped"; message: string }

export async function loadAccountFlow(
  kind: NativeAccountFlowKind,
  env: Readonly<Record<string, string | undefined>>,
  flow: string | string[] | undefined,
  cookie: string,
  transport: typeof globalThis.fetch = globalThis.fetch
): Promise<NativeAccountFlowView> {
  try {
    const config = accountConfig(env)
    const id = singleParameter(flow, "flow")
    if (id === undefined)
      return {
        kind: "start",
        redirectTo: `${config.publicOrigin}/self-service/${kind}/browser`,
      }

    if (kind === "settings") {
      const current = await readSettingsFlow(config, id, cookie, transport)
      return {
        kind: "ready",
        ui: current.flow.ui,
        flowId: current.flow.id,
        publicOrigin: config.publicOrigin,
        completionMessages: current.completionMessages,
      }
    }
    const current =
      kind === "registration"
        ? await readRegistrationFlow(config, id, cookie, transport)
        : kind === "verification"
          ? await readVerificationFlow(config, id, cookie, transport)
          : await readRecoveryFlow(config, id, cookie, transport)
    const state: unknown = "state" in current ? current.state : undefined
    return {
      kind: "ready",
      ui: current.ui,
      flowId: id,
      publicOrigin: config.publicOrigin,
      ...(kind === "verification" && state === "passed_challenge"
        ? { verificationState: "passed_challenge" as const }
        : {}),
    }
  } catch {
    return {
      kind: "stopped",
      message:
        "This account operation expired or could not be checked. Start the account task again.",
    }
  }
}
