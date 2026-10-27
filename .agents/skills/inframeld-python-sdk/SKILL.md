---
name: inframeld-python-sdk
description: Explains and maintains Inframeld's generated Python SDK, HTTPX/Pydantic behavior and generator patches. Use for Python SDK consumption, qualification or upgrades.
---

# Inframeld Python SDK

Help a developer use the OpenAPI Generator HTTPX client with Pydantic models and the repository's built-in resource patches. [ADR-0089](../../../docs/adr/ADR-0089-select-patched-typescript-and-python-sdk-generators.md) selects this approach. The unpublished `inframeld-sdk` distribution imports as `inframeld_sdk`. Version 0.0.0 and private publication metadata remain.

## Working model

Alice calls [get_current_session_with_http_info](../../../packages/sdk-python/generated/inframeld_sdk/api/access_api.py). The detailed result keeps its generated model in `data`, with `status_code`, headers and raw response data. A malformed response remains an exception with available HTTP context and its decoding cause. A 200 status is insufficient to declare success after decoding fails.

The generated synchronous variant bridges to the async implementation. It is not a separate synchronous transport. Inspect the generated method and client lifecycle before proposing a call, particularly when closing a client used through that bridge.

## Essential constraints

- Use the promoted package with the selected patched OpenAPI Generator configuration. Alternative implementations are retired, with their dated findings retained.
- Preserve generated Pydantic validation, boolean constants and the distinction between absent fields and explicit null. A type cast alone does not validate received JSON.
- Keep native detailed results and inspectable errors. Caller configuration supplies base URL/credentials and buffered defaults of five seconds. Scalar timeout overrides retain a total deadline, while explicit tuples retain HTTPX phase budgets. Keep no automatic redirects or redispatch after an uncertain response.
- Patch verified generator resources before generation. Do not edit generated Python, introduce handwritten HTTP methods or repair requests/results in a qualification driver.
- Keep the distributable package independent of backend modules and generator tooling. Java is generation tooling, not a Python SDK runtime dependency. Preserve private publication metadata.

## Read only what the task needs

Start ordinary consumption with the relevant generated operation and [model definitions](../../../packages/sdk-python/generated/inframeld_sdk/models). Read [usage and maintenance](references/usage-and-maintenance.md) for model fidelity, lifecycle, packaging or language-specific generator work. For patches/upgrades/retirement also read [shared maintenance](../inframeld-sdks/references/generator-maintenance.md). For endpoint coverage use [shared qualification](../inframeld-sdks/references/shared-qualification.md).

The [runbook](../../../packages/sdk-tools/README.md) owns commands and setup. Dated [comparison evidence](../../../docs/development/reports/typescript-python-sdk-generator-comparison.md) does not qualify every future API shape or event loop. Coding Standards applies to repository code work, while backend-only declarations are not imposed on this client. Loading this skill authorizes no edits, publication or external actions.
