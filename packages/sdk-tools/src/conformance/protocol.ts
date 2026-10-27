import { z } from "zod";

export const profileSchema = z.enum([
  "rust",
  "typescript-node",
  "typescript-chromium",
  "python-sync",
  "python-async",
]);
export const operations = [
  "getHealth",
  "getCurrentSession",
  "inspectHumanOAuthConsent",
  "decideHumanOAuthConsent",
  "assignProjectUseOnlyGrant",
  "contractFixturePayload",
  "contractFixturePage",
  "contractFixtureUpload",
  "contractFixtureNullable",
  "contractFixtureEmpty",
  "contractFixtureVariants",
  "contractFixtureMedia",
  "contractFixtureFallback",
] as const;
export type Operation = (typeof operations)[number];
export type JsonValue = z.infer<ReturnType<typeof z.json>>;
export const faultSchema = z.object({
  kind: z.enum([
    "none",
    "json",
    "raw",
    "malformed",
    "unexpected",
    "redirect",
    "slow",
    "disconnect",
  ]),
  body: z.json().optional(),
  status: z.number().int().optional(),
  bodyBase64: z.string().optional(),
  contentType: z.string().nullable().optional(),
  headers: z.array(z.tuple([z.string(), z.string()])).optional(),
});
export const callSchema = z.object({
  id: z.string(),
  operation: z.enum(operations),
  headers: z.record(z.string(), z.string()),
  timeout: z.number().int().positive(),
  body: z.record(z.string(), z.json()).optional(),
  query: z.record(z.string(), z.union([z.string(), z.number()])).optional(),
  path: z.record(z.string(), z.string()).optional(),
  uncheckedModel: z.boolean().optional(),
});
export type SdkCall = z.infer<typeof callSchema>;
export const driverRequestSchema = z.strictObject({
  version: z.literal(2),
  profile: profileSchema,
  caseId: z.string(),
  baseUrl: z.url(),
  calls: z.array(callSchema).min(1),
});
export type DriverRequest = z.infer<typeof driverRequestSchema>;
const wireValue = z.object({
  encoding: z.enum(["utf8", "base64"]),
  value: z.string(),
});
const metadata = {
  callId: z.string(),
  status: z.number().int().optional(),
  body: z.json().optional(),
  validation: z.enum([
    "generated-model",
    "generated-schema",
    "parsed-json",
    "none",
  ]),
  headers: z.array(wireValue.extend({ name: z.string() })),
  raw: wireValue.optional(),
  responseType: z.string().optional(),
};
export const observationSchema = z.discriminatedUnion("kind", [
  z.strictObject({ ...metadata, kind: z.literal("success") }),
  z.strictObject({
    ...metadata,
    kind: z.literal("sdk-error"),
    error: z.string(),
    cause: z.string().optional(),
  }),
]);
export type Observation = z.infer<typeof observationSchema>;
export const driverReplySchema = z.discriminatedUnion("kind", [
  z.strictObject({
    version: z.literal(2),
    profile: profileSchema,
    caseId: z.string(),
    kind: z.literal("observations"),
    observations: z.array(observationSchema),
  }),
  z.strictObject({
    version: z.literal(2),
    profile: profileSchema,
    caseId: z.string(),
    kind: z.literal("driver-error"),
    error: z.string(),
  }),
]);
export type DriverReply = z.infer<typeof driverReplySchema>;

export function parseDriverReply(
  request: DriverRequest,
  value: unknown,
): Observation[] {
  const reply = driverReplySchema.parse(value);
  if (reply.profile !== request.profile || reply.caseId !== request.caseId)
    throw new Error("Wrong native profile/case identity");
  if (reply.kind === "driver-error")
    throw new Error(`Native driver failed: ${reply.error}`);
  const ids = reply.observations.map((entry) => entry.callId);
  if (
    ids.length !== request.calls.length ||
    new Set(ids).size !== ids.length ||
    request.calls.some((call) => !ids.includes(call.id))
  )
    throw new Error("Incomplete native result inventory");
  return reply.observations;
}

/** Trusted module boundary shared by Node and browser execution. */
export interface NativeDriver {
  bindings: readonly string[];
  execute(request: DriverRequest, signal?: AbortSignal): Promise<DriverReply>;
}
