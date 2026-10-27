import type { Profile } from "../config.ts";
import type {
  JsonValue,
  Observation,
  Operation,
  SdkCall,
  faultSchema,
} from "./protocol.ts";
import type { z } from "zod";

export interface CallResult {
  observation: Observation;
  witness: Record<string, JsonValue>;
}
export type CaseCall = Omit<SdkCall, "id"> & {
  fault?: z.infer<typeof faultSchema>;
};
export interface CaseContext {
  profile: Profile;
  origin: string;
  call(input: CaseCall): Promise<CallResult>;
  sequence(inputs: CaseCall[]): Promise<CallResult[]>;
}
export interface SdkCase {
  id: string;
  operation: Operation;
  outcome: "success" | "failure";
  expectedCalls?: number;
  run(context: CaseContext): Promise<void>;
}
export const cases: SdkCase[] = [];

/** Register metadata once, beside an ordinary test body with visible assertions. */
export function sdkTest(
  metadata: Omit<SdkCase, "run">,
  run: SdkCase["run"],
): void {
  if (cases.some((entry) => entry.id === metadata.id))
    throw new Error(`Duplicate scenario ${metadata.id}`);
  cases.push({ ...metadata, run });
}
