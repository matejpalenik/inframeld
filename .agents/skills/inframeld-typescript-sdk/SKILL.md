---
name: inframeld-typescript-sdk
description: Explains and maintains Inframeld's generated TypeScript SDK, Fetch/Zod behavior and generator patches. Use for TypeScript SDK consumption, qualification or upgrades.
---

# Inframeld TypeScript SDK

Help a developer use the Hey API Fetch client with generated Zod response validation and typed failure objects. [ADR-0089](../../../docs/adr/ADR-0089-select-patched-typescript-and-python-sdk-generators.md) selects this configuration. The active package is `@inframeld/sdk`, with version 0.0.0 and private publication protection.

## Working model

Alice calls the generated [getCurrentSession](../../../packages/sdk-typescript/generated/sdk.gen.ts) with her configured client. A valid result carries the generated model in `data` and the native HTTP response in `response`. If the backend returns a number for its UUID string, the generated validator rejects it. The fields result exposes a discriminated `SdkFailure`, available `response` metadata and `rawBody`. Narrow `error.kind === "api"` before accessing its validated `error.body`. Decoding and network failures have distinct kinds. A network failure may have no HTTP response.

Inspect that generated method, its [models](../../../packages/sdk-typescript/generated/types.gen.ts) and native OpenAPI before proposing a call. Consume generated operations rather than copying request/response types or implementing HTTP methods in the application.

## Essential constraints

- Use the promoted package with the selected patched Hey API configuration. Alternative implementations have been removed, while dated results remain historical evidence.
- Preserve the qualified Fetch fields response style, `throwOnError: false` and generated status/media-specific success and declared-error validation. Other response modes need separate qualification before equivalent guarantees are promised.
- Keep caller-controlled base URLs and credentials, five-second buffered defaults and manual redirects. Positive finite `timeoutMs` request overrides take precedence over client values, while caller cancellation combines with the deadline. Deliberate transport overrides change qualified behavior. In browsers, use actual cookie/Origin behavior rather than spoofing forbidden headers.
- Apply generator patches before generation. Do not edit generated TypeScript, weaken native schemas or repair SDK output in drivers. Ordinary builds consume committed source without code generation.
- Do not treat the browser qualification as a delivered login UI or a production CORS deployment check. CLI presentation and credential storage have their own owners.

## Read only what the task needs

Ordinary consumption starts with the relevant generated operation/model. For response modes, browser behavior, packaging or language-specific maintenance, read [usage and maintenance](references/usage-and-maintenance.md). For a patch, upgrade or retirement, also read the [shared generator policy](../inframeld-sdks/references/generator-maintenance.md). For new endpoint coverage, read [shared qualification](../inframeld-sdks/references/shared-qualification.md).

The [runbook](../../../packages/sdk-tools/README.md) owns commands and tooling setup. Configuration, versions and hashes live in its linked source inputs. Dated [comparison evidence](../../../docs/development/reports/typescript-python-sdk-generator-comparison.md) is not a guarantee for future endpoints. Coding Standards applies to code work without importing backend Python conventions. Loading this skill authorizes no edits, publication or external actions.
