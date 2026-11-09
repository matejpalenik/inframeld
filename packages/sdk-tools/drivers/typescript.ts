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
  revokeApplicationKey: (client: Client, call: SdkCall) =>
    sdk.revokeApplicationKey({
      ...options(client, call),
      path: call.path as sdk.RevokeApplicationKeyData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.RevokeApplicationKeyData["body"],
    }),
  issueApplicationKey: (client: Client, call: SdkCall) =>
    sdk.issueApplicationKey({
      ...options(client, call),
      path: call.path as sdk.IssueApplicationKeyData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.IssueApplicationKeyData["body"],
    }),
  issueInvitation: (client: Client, call: SdkCall) =>
    sdk.issueInvitation({
      ...options(client, call),
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.IssueInvitationData["body"],
    }),
  revokeInvitation: (client: Client, call: SdkCall) =>
    sdk.revokeInvitation({
      ...options(client, call),
      path: call.path as sdk.RevokeInvitationData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.RevokeInvitationData["body"],
    }),
  previewInvitation: (client: Client, call: SdkCall) =>
    sdk.previewInvitation({
      ...options(client, call),
      body: call.body as sdk.PreviewInvitationData["body"],
    }),
  activateInvitation: (client: Client, call: SdkCall) =>
    sdk.activateInvitation({
      ...options(client, call),
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.ActivateInvitationData["body"],
    }),

  createAccessGroup: (client: Client, call: SdkCall) =>
    sdk.createAccessGroup({
      ...options(client, call),
      path: call.path as sdk.CreateAccessGroupData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.CreateAccessGroupData["body"],
    }),
  getAccessGroup: (client: Client, call: SdkCall) =>
    sdk.getAccessGroup({
      ...options(client, call),
      path: call.path as sdk.GetAccessGroupData["path"],
    }),
  resolveAccessGroup: (client: Client, call: SdkCall) =>
    sdk.resolveAccessGroup({
      ...options(client, call),
      path: call.path as sdk.ResolveAccessGroupData["path"],
      query: call.query as sdk.ResolveAccessGroupData["query"],
    }),
  listAccessGroupMembers: (client: Client, call: SdkCall) =>
    sdk.listAccessGroupMembers({
      ...options(client, call),
      path: call.path as sdk.ListAccessGroupMembersData["path"],
      query: call.query as sdk.ListAccessGroupMembersData["query"],
    }),
  listAccessGroupManagers: (client: Client, call: SdkCall) =>
    sdk.listAccessGroupManagers({
      ...options(client, call),
      path: call.path as sdk.ListAccessGroupManagersData["path"],
      query: call.query as sdk.ListAccessGroupManagersData["query"],
    }),
  addAccessGroupMember: (client: Client, call: SdkCall) =>
    sdk.addAccessGroupMember({
      ...options(client, call),
      path: call.path as sdk.AddAccessGroupMemberData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.AddAccessGroupMemberData["body"],
    }),
  removeAccessGroupMember: (client: Client, call: SdkCall) =>
    sdk.removeAccessGroupMember({
      ...options(client, call),
      path: call.path as sdk.RemoveAccessGroupMemberData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      query: call.query as sdk.RemoveAccessGroupMemberData["query"],
    }),
  appointAccessGroupManager: (client: Client, call: SdkCall) =>
    sdk.appointAccessGroupManager({
      ...options(client, call),
      path: call.path as sdk.AppointAccessGroupManagerData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.AppointAccessGroupManagerData["body"],
    }),
  removeAccessGroupManager: (client: Client, call: SdkCall) =>
    sdk.removeAccessGroupManager({
      ...options(client, call),
      path: call.path as sdk.RemoveAccessGroupManagerData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      query: call.query as sdk.RemoveAccessGroupManagerData["query"],
    }),
  deleteAccessGroup: (client: Client, call: SdkCall) =>
    sdk.deleteAccessGroup({
      ...options(client, call),
      path: call.path as sdk.DeleteAccessGroupData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      query: call.query as sdk.DeleteAccessGroupData["query"],
    }),

  listOrganizationActionGrants: (client: Client, call: SdkCall) =>
    sdk.listOrganizationActionGrants({
      ...options(client, call),
      path: call.path as sdk.ListOrganizationActionGrantsData["path"],
      query: call.query as sdk.ListOrganizationActionGrantsData["query"],
    }),
  setOrganizationActionGrant: (client: Client, call: SdkCall) =>
    sdk.setOrganizationActionGrant({
      ...options(client, call),
      path: call.path as sdk.SetOrganizationActionGrantData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.SetOrganizationActionGrantData["body"],
    }),
  removeOrganizationActionGrant: (client: Client, call: SdkCall) =>
    sdk.removeOrganizationActionGrant({
      ...options(client, call),
      path: call.path as sdk.RemoveOrganizationActionGrantData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      query: call.query as sdk.RemoveOrganizationActionGrantData["query"],
    }),
  listAccessGroupActionGrants: (client: Client, call: SdkCall) =>
    sdk.listAccessGroupActionGrants({
      ...options(client, call),
      path: call.path as sdk.ListAccessGroupActionGrantsData["path"],
      query: call.query as sdk.ListAccessGroupActionGrantsData["query"],
    }),
  setAccessGroupActionGrant: (client: Client, call: SdkCall) =>
    sdk.setAccessGroupActionGrant({
      ...options(client, call),
      path: call.path as sdk.SetAccessGroupActionGrantData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.SetAccessGroupActionGrantData["body"],
    }),
  removeAccessGroupActionGrant: (client: Client, call: SdkCall) =>
    sdk.removeAccessGroupActionGrant({
      ...options(client, call),
      path: call.path as sdk.RemoveAccessGroupActionGrantData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      query: call.query as sdk.RemoveAccessGroupActionGrantData["query"],
    }),
  listApplicationAccountActionGrants: (client: Client, call: SdkCall) =>
    sdk.listApplicationAccountActionGrants({
      ...options(client, call),
      path: call.path as sdk.ListApplicationAccountActionGrantsData["path"],
      query: call.query as sdk.ListApplicationAccountActionGrantsData["query"],
    }),
  setApplicationAccountActionGrant: (client: Client, call: SdkCall) =>
    sdk.setApplicationAccountActionGrant({
      ...options(client, call),
      path: call.path as sdk.SetApplicationAccountActionGrantData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.SetApplicationAccountActionGrantData["body"],
    }),
  removeApplicationAccountActionGrant: (client: Client, call: SdkCall) =>
    sdk.removeApplicationAccountActionGrant({
      ...options(client, call),
      path: call.path as sdk.RemoveApplicationAccountActionGrantData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      query: call.query as sdk.RemoveApplicationAccountActionGrantData["query"],
    }),
  listProjectGrantRecipients: (client: Client, call: SdkCall) =>
    sdk.listProjectGrantRecipients({
      ...options(client, call),
      path: call.path as sdk.ListProjectGrantRecipientsData["path"],
      query: call.query as sdk.ListProjectGrantRecipientsData["query"],
    }),
  getMyProjectAccess: (client: Client, call: SdkCall) =>
    sdk.getMyProjectAccess({
      ...options(client, call),
      path: call.path as sdk.GetMyProjectAccessData["path"],
      query: call.query as sdk.GetMyProjectAccessData["query"],
    }),
  setProjectActionGrant: (client: Client, call: SdkCall) =>
    sdk.setProjectActionGrant({
      ...options(client, call),
      path: call.path as sdk.SetProjectActionGrantData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.SetProjectActionGrantData["body"],
    }),
  removeProjectActionGrant: (client: Client, call: SdkCall) =>
    sdk.removeProjectActionGrant({
      ...options(client, call),
      path: call.path as sdk.RemoveProjectActionGrantData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      query: call.query as sdk.RemoveProjectActionGrantData["query"],
    }),
  addProjectMember: (client: Client, call: SdkCall) =>
    sdk.addProjectMember({
      ...options(client, call),
      path: call.path as sdk.AddProjectMemberData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.AddProjectMemberData["body"],
    }),
  removeProjectMember: (client: Client, call: SdkCall) =>
    sdk.removeProjectMember({
      ...options(client, call),
      path: call.path as sdk.RemoveProjectMemberData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      query: call.query as sdk.RemoveProjectMemberData["query"],
    }),
  admitHuman: (client: Client, call: SdkCall) =>
    sdk.admitHuman({
      ...options(client, call),
      path: call.path as sdk.AdmitHumanData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.AdmitHumanData["body"],
    }),
  createApplicationAccount: (client: Client, call: SdkCall) =>
    sdk.createApplicationAccount({
      ...options(client, call),
      path: call.path as sdk.CreateApplicationAccountData["path"],
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.CreateApplicationAccountData["body"],
    }),
  getApplicationAccount: (client: Client, call: SdkCall) =>
    sdk.getApplicationAccount({
      ...options(client, call),
      path: call.path as sdk.GetApplicationAccountData["path"],
    }),
  resolveApplicationAccount: (client: Client, call: SdkCall) =>
    sdk.resolveApplicationAccount({
      ...options(client, call),
      path: call.path as sdk.ResolveApplicationAccountData["path"],
      query: call.query as sdk.ResolveApplicationAccountData["query"],
    }),
  listApplicationKeys: (client: Client, call: SdkCall) =>
    sdk.listApplicationKeys({
      ...options(client, call),
      path: call.path as sdk.ListApplicationKeysData["path"],
      query: call.query as sdk.ListApplicationKeysData["query"],
    }),
  getApplicationKey: (client: Client, call: SdkCall) =>
    sdk.getApplicationKey({
      ...options(client, call),
      path: call.path as sdk.GetApplicationKeyData["path"],
    }),
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
  resolveProjectName: (client: Client, call: SdkCall) =>
    sdk.resolveProjectName({
      ...options(client, call),
      path: call.path as { name: string },
    }),
  getProjectMetadata: (client: Client, call: SdkCall) =>
    sdk.getProjectMetadata({
      ...options(client, call),
      path: call.path as { project_id: string },
    }),
  listProjectMembers: (client: Client, call: SdkCall) =>
    sdk.listProjectMembers({
      ...options(client, call),
      path: call.path as { project_id: string },
      query: call.query as sdk.ListProjectMembersData["query"],
    }),
  listProjectActionGrants: (client: Client, call: SdkCall) =>
    sdk.listProjectActionGrants({
      ...options(client, call),
      path: call.path as sdk.ListProjectActionGrantsData["path"],
      query: call.query as sdk.ListProjectActionGrantsData["query"],
    }),
  updateProjectMetadata: (client: Client, call: SdkCall) =>
    sdk.updateProjectMetadata({
      ...options(client, call),
      path: call.path as { project_id: string },
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.UpdateProjectMetadataData["body"],
    }),
  getHealth: (client: Client, call: SdkCall) =>
    sdk.getHealth(options(client, call)),
  getCurrentSession: (client: Client, call: SdkCall) =>
    sdk.getCurrentSession(options(client, call)),
  getCurrentApplicationSession: (client: Client, call: SdkCall) =>
    sdk.getCurrentApplicationSession(options(client, call)),
  getMyOrganizationAccess: (client: Client, call: SdkCall) =>
    sdk.getMyOrganizationAccess(options(client, call)),
  createProject: (client: Client, call: SdkCall) =>
    sdk.createProject({
      ...options(client, call),
      headers: {
        ...call.headers,
        "Idempotency-Key": call.headers["Idempotency-Key"]!,
      },
      body: call.body as sdk.CreateProjectData["body"],
    }),
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
  getDeletionStatus: (client: Client, call: SdkCall) =>
    sdk.getDeletionStatus({
      ...options(client, call),
      query: call.query as sdk.GetDeletionStatusData["query"],
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
