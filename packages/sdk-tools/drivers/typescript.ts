/** Native Fetch calls only. Test expectations live in the feature tests. */
import * as sdk from "@inframeld/sdk";
import * as fixtures from "../fixtures/typescript/generated/sdk.gen.ts";
import type { ContractFixturePayload } from "../fixtures/typescript/generated/types.gen.ts";
import type {
  DriverReply,
  Observation,
  SdkCall,
} from "../src/conformance/protocol.ts";

import { z } from "zod";
import { driverRequestSchema } from "../src/conformance/protocol.ts";

type Client = ReturnType<typeof sdk.createClient>;
interface Result {
  data?: unknown;
  error?: sdk.SdkFailure<unknown>;
  response?: Response;
  rawBody?: string;
}
const options = (client: Client, call: SdkCall, signal?: AbortSignal) => ({
  client,
  headers: call.headers,
  redirect: "manual" as const,
  credentials: "include" as const,
  signal: AbortSignal.any([
    AbortSignal.timeout(call.timeout),
    ...(signal ? [signal] : []),
  ]),
  throwOnError: false as const,
  responseStyle: "fields" as const,
});

// Cast only the validated test-protocol input at the generated API boundary.
// Request validation remains the generator's qualified policy, not a driver repair.
const calls = {
  getProtectedResourceMetadata: (client: Client, call: SdkCall) =>
    sdk.getProtectedResourceMetadata(options(client, call)),
  getProtectedResourceMetadataForPath: (client: Client, call: SdkCall) =>
    sdk.getProtectedResourceMetadataForPath({
      ...options(client, call),
      path: call.path as { resource_path: string },
    }),
  contractFixtureVariants: (client: Client, call: SdkCall) =>
    fixtures.contractFixtureVariants({
      ...options(client, call),
      query: call.query,
    }),
  contractFixtureFallback: (client: Client, call: SdkCall) =>
    fixtures.contractFixtureFallback({
      ...options(client, call),
      query: call.query,
    }),
  contractFixtureMedia: (client: Client, call: SdkCall) =>
    fixtures.contractFixtureMedia(options(client, call)),
  getHealth: (client: Client, call: SdkCall) =>
    sdk.getHealth(options(client, call)),
  getCurrentSession: (client: Client, call: SdkCall) =>
    sdk.getCurrentSession(options(client, call)),
  inspectHumanOAuthConsent: (client: Client, call: SdkCall) =>
    sdk.inspectHumanOAuthConsent({
      ...options(client, call),
      query: call.query as { consent_challenge: string },
    }),
  decideHumanOAuthConsent: (client: Client, call: SdkCall) =>
    sdk.decideHumanOAuthConsent({
      ...options(client, call),
      body: call.body as sdk.DecideHumanOAuthConsentData["body"],
    }),
  lookupOriginalOperation: (client: Client, call: SdkCall) =>
    sdk.lookupOriginalOperation({
      ...options(client, call),
      body: call.body as sdk.LookupOriginalOperationData["body"],
    }),
  assignProjectUseOnlyGrant: (client: Client, call: SdkCall) =>
    sdk.assignProjectUseOnlyGrant({
      ...options(client, call),
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.AssignProjectUseOnlyGrantData["body"],
      path: call.path as { project_id: string },
    }),
  contractFixtureNullable: (client: Client, call: SdkCall) =>
    fixtures.contractFixtureNullable(options(client, call)),
  contractFixtureEmpty: (client: Client, call: SdkCall) =>
    fixtures.contractFixtureEmpty(options(client, call)),
  contractFixturePayload: (client: Client, call: SdkCall) =>
    fixtures.contractFixturePayload({
      ...options(client, call),
      body: call.body as unknown as ContractFixturePayload,
    }),
  contractFixturePage: (client: Client, call: SdkCall) =>
    fixtures.contractFixturePage({
      ...options(client, call),
      query: call.query,
    }),
  contractFixtureUpload: (client: Client, call: SdkCall) => {
    const body = call.body!;
    const bytes = Uint8Array.from(
      atob(z.string().parse(body.fileBase64)),
      (character) => character.charCodeAt(0),
    );
    return fixtures.contractFixtureUpload({
      ...options(client, call),
      body: {
        file: new File([bytes], z.string().parse(body.fileName), {
          type: "application/octet-stream",
        }),
        label: z.string().parse(body.label),
      },
    });
  },
};
export const bindings = Object.keys(calls);

async function observe(client: Client, call: SdkCall): Promise<Observation> {
  let result: Result;
  const pending = calls[call.operation](client, call);
  try {
    result = await pending;
  } catch (error) {
    return {
      kind: "sdk-error",
      callId: call.id,
      validation: "none",
      headers: [],
      error: String(error),
      ...(error instanceof Error && error.cause
        ? { cause: String(error.cause) }
        : {}),
    };
  }
  const failed = Object.hasOwn(result, "error");
  const error = result.error;
  const body = failed
    ? error && (error.kind === "api" || error.kind === "http")
      ? error.body
      : undefined
    : result.data;
  const metadata: Omit<Observation, "kind"> = {
    callId: call.id,
    validation: failed
      ? error?.kind === "api"
        ? "generated-schema"
        : error?.kind === "http" && body !== undefined
          ? "parsed-json"
          : "none"
      : result.data === undefined
        ? "none"
        : "generated-schema",
    headers: result.response
      ? [...result.response.headers.entries()]
          .filter(([name]) => name !== "set-cookie")
          .map(([name, value]) => ({ name, encoding: "utf8" as const, value }))
          .concat(
            (result.response.headers.getSetCookie?.() ?? []).map((value) => ({
              name: "set-cookie",
              encoding: "utf8" as const,
              value,
            })),
          )
      : [],
    ...(result.response
      ? { status: result.response.status, responseType: result.response.type }
      : {}),
    ...(body !== undefined && !(body instanceof Error)
      ? { body: z.json().parse(body) }
      : {}),
    ...(result.rawBody !== undefined
      ? { raw: { encoding: "utf8" as const, value: result.rawBody } }
      : {}),
  };
  return failed
    ? {
        ...metadata,
        kind: "sdk-error",
        error: error?.message ?? "SDK failure",
        ...(error && "cause" in error && error.cause
          ? { cause: String(error.cause) }
          : {}),
      }
    : { ...metadata, kind: "success" };
}

export async function execute(
  input: unknown,
  signal?: AbortSignal,
): Promise<DriverReply> {
  const request = driverRequestSchema.parse(input);
  if (
    request.profile !== "typescript-node" &&
    request.profile !== "typescript-chromium"
  )
    throw new Error("Unsupported TypeScript driver profile");
  const client = sdk.createClient({
    baseUrl: request.baseUrl,
    ...(signal
      ? {
          fetch: (input, init) =>
            fetch(input, {
              ...init,
              signal: AbortSignal.any([
                signal,
                ...(init?.signal ? [init.signal] : []),
                ...(input instanceof Request ? [input.signal] : []),
              ]),
            }),
        }
      : {}),
  });
  const observations: Observation[] = [];
  try {
    for (const call of request.calls)
      observations.push(await observe(client, call));
  } catch (error) {
    return {
      version: 2,
      profile: request.profile,
      caseId: request.caseId,
      kind: "driver-error",
      error: String(error),
    };
  }
  return {
    version: 2,
    profile: request.profile,
    caseId: request.caseId,
    kind: "observations",
    observations,
  };
}
