# Debug a request without repeating its effects

<a id="debug-a-request-without-repeating-its-effects"></a>

Alice submits a grant, loses the response and sees an error. First determine which boundary failed. A missing response does not prove that the database rolled back or that a model provider did nothing.

1. Keep the request ID and original operation identity. Inspect the permitted current outcome before trying a new operation. A request ID correlates diagnostics, while an operation ID identifies durable work.
2. Check the local API and dependency health. Use `pnpm dev:db:status` for development services. For isolated integration logs, follow [testing](testing.md). Do not publish provider administration ports to make debugging easier.
3. Distinguish credential verification, local admission and authorization. A valid Hydra token can still identify an unadmitted or blocked human. A principal ID alone grants no permission. Follow [browser and bearer dispatch](../../../.agents/skills/inframeld-access-models/references/browser-sessions.md).
4. Read sanitized diagnostics using [the reporting contract](../../../.agents/skills/inframeld-application-contracts/references/safe-diagnostics.md). Do not print tokens, raw exception messages, prompts, source content or SQL values. Public problems intentionally contain safe descriptions rather than provider internals.
5. Inspect saved work with [jobs and recovery](../../../.agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md). Cancellation is a request, not proof that an external call stopped. A lost paid response needs reconciliation, not an automatic retry.
6. Keep query tracing separate from required business records. Optional trace failure can leave an otherwise successful answer with incomplete diagnostics. Do not reconstruct a hidden content cache. See [trace privacy](../../../.agents/skills/inframeld-pipelines/references/query-tracing-and-privacy.md).

For a local schema mismatch, use the documented [upgrade procedure](../operations/upgrades.md). Starting the API never runs migrations. Diagnosis should report what is known, unknown and safe to inspect. It must not silently repair accounts, reset storage or replay work.
