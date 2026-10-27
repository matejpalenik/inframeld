import type { Language } from "../config.ts";

export interface Patch {
  file: string;
  sha256: string;
}
export interface GeneratorSourcePin {
  upstreamVersion: string;
  archiveUrl: string;
  archiveFile?: string;
  archiveRoot?: string;
  archiveSha256: string;
  revision?: string;
  patches: Patch[];
}
export interface GeneratorPin extends GeneratorSourcePin {
  sharedParser?: GeneratorSourcePin;
}
export interface PreparedSource {
  pins: GeneratorPin;
  archive: string;
  destination: string;
  patches: (Patch & { path: string })[];
}
export interface GenerationTarget {
  kind: "production" | "fixtures" | "capabilities";
  directory: string;
  schema: string;
  metadata?: boolean;
}
export interface Generator {
  prepare(test?: boolean): Promise<string>;
  emit(
    target: GenerationTarget,
    tool: string,
    destination: string,
  ): Promise<void>;
}
export type GeneratorManifest = Record<Language, GeneratorPin>;
