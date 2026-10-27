import type { ConsumerEvidence } from "../packaging/evidence.ts";
import type { Language } from "../config.ts";
import { archiveRust, consumeRust } from "../packaging/rust.ts";
import {
  archiveTypescript,
  consumeTypescript,
} from "../packaging/typescript.ts";
import { archivePython, consumePython } from "../packaging/python.ts";

export async function buildArchive(
  language: Language,
  work: string,
): Promise<string> {
  return {
    rust: archiveRust,
    typescript: archiveTypescript,
    python: archivePython,
  }[language](work);
}

export async function consumePackage(
  language: Language,
  work: string,
  archive: string,
  baseUrl: string,
): Promise<ConsumerEvidence> {
  return {
    rust: consumeRust,
    typescript: consumeTypescript,
    python: consumePython,
  }[language](work, archive, baseUrl);
}
