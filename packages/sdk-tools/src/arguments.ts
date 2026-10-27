import { parseArgs } from "node:util";
import { languages, profiles, type Language } from "./config.ts";
import { profileSchema } from "./conformance/protocol.ts";

export function argumentsFor(argv: string[]) {
  const { values, positionals } = parseArgs({
    args: argv,
    allowPositionals: true,
    options: { profile: { type: "string" }, case: { type: "string" } },
  });
  const [action, ...selection] = positionals;
  if (
    !action ||
    !["setup", "generate", "check", "test", "verify"].includes(action)
  )
    throw new Error(
      "Use sdk:setup, sdk:generate, sdk:check, sdk:test or sdk:verify",
    );
  if (action !== "test" && (values.profile || values.case))
    throw new Error(
      "Profile/case filters are local sdk:test selections, not complete verification",
    );
  const profile = values.profile
    ? profileSchema.parse(values.profile)
    : undefined;
  const inferred = profile
    ? languages.filter((language) =>
        (profiles[language] as readonly string[]).includes(profile),
      )
    : languages;
  const selected = (selection.length ? selection : inferred).map((value) => {
    if (!languages.includes(value as Language))
      throw new Error(`Unknown SDK ${value}`);
    return value as Language;
  });
  if (new Set(selected).size !== selected.length)
    throw new Error("Duplicate SDK selection");
  if (
    profile &&
    selected.some(
      (language) =>
        !(profiles[language] as readonly string[]).includes(profile),
    )
  )
    throw new Error("Profile does not belong to the selected SDK");
  return {
    action,
    selected,
    profile,
    caseId: values.case,
    partial: Boolean(profile || values.case),
  };
}
