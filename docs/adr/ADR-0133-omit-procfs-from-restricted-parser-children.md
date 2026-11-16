# ADR-0133: Omit procfs from restricted parser children

**Status:** Accepted

**Date:** 2026-11-16

## Context and Problem Statement

Parsing Alice's PDF requires enough operating-system access to load the approved converter and its assets. The trusted supervisor needs process information to set up the sandbox and confirm that Alice's attempt has ended. The restricted converter has a narrower job.

Docker masks sensitive entries in its container process filesystem. Linux can reject an unprivileged nested procfs mount when the inherited view has those locked masks. Preserving the approved child procfs view would require a different protected container mount layout.

## Considered Options

- Omit the restricted child's procfs mount. Keep process observation in the trusted supervisor and qualify the converter under that boundary.
- Provide a private procfs inside the child. Qualify a compatible parent mount layout that preserves the effective protections of the stock container masks.

## Decision Outcome

Omit procfs from the restricted parser child. The trusted supervisor uses its own confined procfs for fixed setup and process observation. Before accepting results, verify the required namespaces, privilege and host policy enforcement, and complete termination and reaping of the owned attempt. Fail closed when a required observation is missing.

This decision supersedes the private child procfs detail in the workflow linked by ADR-0034 and ADR-0120. The [approved parser profile](../../.agents/skills/inframeld-indexing/references/decision-parser-runtime-profile.md#approved-resolution) owns the isolation controls, limits, and qualification.

## Consequences

Twelve trusted Linux ARM64 converter tests passed with procfs masked, including the Alice excerpt and a ruled table. This establishes that those conversions run without procfs. The restricted Bubblewrap child, hostile-input cases, and the supported Ubuntu and managed Mac runtimes each require native qualification. A pinned converter that needs procfs fails qualification under this profile.

## Links

- [ADR-0034: Restricted processing boundary](ADR-0034-process-untrusted-documents-inside-a-restricted-execution-boundary.md)
- [ADR-0120: Conservative parser profile](ADR-0120-qualify-one-conservative-offline-parser-profile.md)
- [Parser mount and lifetime controls](../../.agents/skills/inframeld-indexing/references/parser-isolation-and-validation.md#expose-only-what-this-document-needs)
- [Linux mount visibility check](https://github.com/torvalds/linux/blob/v6.8/fs/namespace.c#L4982)
