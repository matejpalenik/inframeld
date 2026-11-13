# ADR-0132: Scope local reset to the managed installation

**Status:** Accepted

**Date:** 2026-11-13

## Context and Problem Statement

Alice wants to repeat first sign-in on her Mac. Her CLI also has a saved connection and login for a remote installation. A factory reset needs to give her a fresh local installation without losing the ability to return to that remote work.

The previous managed-runtime contract included all of the current user's Inframeld CLI state in a factory reset. That made a command in the `local` family affect credentials and preferences outside the installation it addresses.

## Considered Options

- Reset the managed installation and all CLI state for this OS user. This would return the entire CLI to a fresh state and remove the user's local copies of remote connections and credentials.
- Reset the managed installation and its bound CLI state. This lets the user repeat local setup while retaining remote context. Cleanup must identify the removed installation precisely.

## Decision Outcome

Scope `inframeld local reset` to the one verified managed installation. This supersedes the prior whole-CLI reset scope in the managed-runtime, target selection and trace deletion contracts.

Preview the owned stack and the local state bound to it before the user confirms. Confirm shutdown before removing the stack's data and credentials. A reset interrupted or only partially completed retains enough ownership information to inspect and remove the remainder under the same scope. A completed reset leaves the stack stopped. The next explicit start initializes a new installation identity.

## Consequences

Remote target definitions, remote login copies and their selections survive a local reset. The CLI clears a selection only when it points to the removed installation and offers no fallback selection. Credential writes for that installation must be fenced so an in-flight login or refresh cannot restore a removed binding.

The command, its confirmation interface and native cleanup qualification are still delivery work.

## Links

- [Managed lifecycle and reset](../../.agents/skills/inframeld-application-contracts/references/cli-local-runtime.md#persistent-lifecycle-status-and-deliberate-reset)
- [CLI target and account selection](../../.agents/skills/inframeld-application-contracts/references/cli-targets-and-accounts.md)
- [Local factory reset delivery](https://github.com/matejpalenik/inframeld/issues/164)
