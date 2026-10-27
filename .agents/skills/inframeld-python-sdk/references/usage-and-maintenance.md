# Consume and maintain the Python client

Alice omits an optional nullable request field. The SDK must preserve that absence instead of supplying null. The selected Pydantic client checks received values and uses patched generator resources to preserve field presence, native boolean enums and inspectable decoding failures.

## Native models and results

Read the [generated APIs](../../../../packages/sdk-python/generated/inframeld_sdk/api/access_api.py), [models](../../../../packages/sdk-python/generated/inframeld_sdk/models), [API response](../../../../packages/sdk-python/generated/inframeld_sdk/api_response.py) and [exceptions](../../../../packages/sdk-python/generated/inframeld_sdk/exceptions.py) for exact signatures. Do not copy a backend DTO into the public client or assume that an attrs-based candidate has the same runtime checks.

A required nullable field must be present even when its value is null. An optional nullable field may be absent or explicitly null. Native boolean `false` differs from the string `"false"`. The generated strict scalar models must reject a boolean or array where the contract permits only a string/integer union. These distinctions have retained model and wire regressions.

The native driver uses Pydantic's unchecked `model_construct` only for the intentionally invalid grant request that tests the server's validation response. This does not qualify bypassing validation for ordinary consumption. Native model probes and normal constructed requests establish the separate model guarantees.

Detailed success results keep `data`, status, native HTTPX `Headers` and raw response data together. Repeated headers remain accessible through `get_list`, and JSON serialization emits ordered name/value pairs. Exceptions retain exact available `raw_data` separately from decoded `body` diagnostics and preserve decoding causes. Typed HTTP errors may expose generated Problem Details. A decoding error can retain an HTTP 200 response through an `ApiException`, so status alone cannot identify success or determine the error's category. Inspect available native metadata and the underlying cause without retrying to recover it. Transport failures may have no response.

## Sync and async lifecycle

Response selection matches exact status before class/default, then exact media type before wildcards. JSON requires valid JSON even for scalar strings and an unambiguous missing content type. Array/map shapes are checked before conversion into generated models. Precise native annotations retain status/media model alternatives, null and body absence. Optional non-nullable properties reject supplied null through both native validation and decoding. Omission does not authorize replacing an explicit null with a default. Python generation emits library source without repository CI templates.

Buffered operations default to five seconds. Default/scalar `_request_timeout` values impose a total buffered network/body deadline and use native HTTPX timeout exceptions. Explicit `(connect, read)` tuples preserve phase budgets, which do not imply a total elapsed deadline. Caller cancellation remains distinct from deadline expiration. Deliberate transport overrides change the qualified policy.

The [API client](../../../../packages/sdk-python/generated/inframeld_sdk/api_client.py) has an asynchronous close operation. Generated sync methods use [run_sync](../../../../packages/sdk-python/generated/inframeld_sdk/sync_helper.py) and its background event loop. The [qualification driver](../../../../packages/sdk-tools/drivers/python/main.py) closes sync-used transports on that generated loop. Async use follows the client's async lifecycle.

Do not present the bridge as an independently generated synchronous HTTPX client or assume it is safe to invoke blocking sync methods inside an async application loop. Native regressions cover async operation cancellation, recovery and used-pool closure. Installed consumers exercise real requests on both sync/async lifecycles. The public sync bridge has no equivalent operation-cancellation API. Alternate event loops and broader concurrency/streaming promises remain outside qualification. Inspect the actual helpers when adapting lifecycle rather than inventing a wrapper or a second HTTP transport.

## Generator resources and package boundary

The [runner](../../../../packages/sdk-tools/src/generation/python.ts) owns library/options selection. The [tooling lock](../../../../packages/sdk-tools/requirements.lock) and its inputs own the isolated Python versions. The [patch manifest](../../../../packages/sdk-tools/generators/manifest.json) owns the original generator archive and ordered patch identities. These are the pin authorities rather than this guide.

The selected generator preparation patches the explicit resource list in the Python adapter inside a copied, verified generator JAR. The changes correct boolean enum comparisons, preserve field presence, reject invalid primitive/null/undeclared-success responses, retain root response nullability and expose accurate native call/exception annotations. Read the resource list and ordered manifest rather than assuming a fixed count. Java classes are unchanged, and generation uses no replacement custom-template directory. No emitted Python source is patched afterward. Follow [shared maintenance](../../inframeld-sdks/references/generator-maintenance.md) for regression-first changes, provenance failures, upgrades and retirement.

The [outer pyproject](../../../../packages/sdk-python/pyproject.toml) owns package metadata, runtime dependencies and `Private :: Do Not Upload`. Generated inner metadata does not own publication. Ordinary wheel builds consume committed source and need no backend, Java or generator installation. Conformance installs the SDK and private fixture wheels in an isolated environment, while the external consumer installs only the production SDK.

## Qualification boundaries

The [native model tests](../../../../packages/sdk-tools/drivers/python/models_test.py) complement HTTP behavior with presence/null, boolean constant and scalar-type cases. Compilation/import success cannot substitute for those checks. Run sync and async profiles independently and retain packaging, drift and native HTTP failures separately.

Read the [dated report](../../../../docs/development/reports/typescript-python-sdk-generator-comparison.md) and [structured evidence](../../../../docs/development/reports/typescript-python-sdk-generator-results.json) for tested artifacts and unrun platforms/protocols. Selection does not establish an upgrade rehearsal, complete provider journey or general streaming guarantee. The [hardening report](../../../../docs/development/reports/sdk-hardening-verification.md) records current source preparation and interpreter/typing evidence separately from pending upgrades and remote platforms. The [shared qualification reference](../../inframeld-sdks/references/shared-qualification.md) describes the implemented runner, coverage and required evidence. Remote platform results still need actual execution. Publication and server-version compatibility remain separate work.

Handwritten drivers, tests and consumers use strict Pyright/Ruff from the isolated tooling lock. Protocol records validate control input, direct bindings call generated methods, and observation conversion validates only the JSON boundary. Expected SDK exceptions remain separate from malformed control input and conversion defects. A type-checking failure requires inspecting the actual generated signature, not adding reflective dispatch, broad ignores or handwritten stubs.

[ADR-0094](../../../../docs/adr/ADR-0094-select-sdk-response-variants-and-safe-transport-defaults.md) records response variants and default deadlines. The [subsequent evidence](../../../../docs/development/reports/sdk-response-fixes-verification.md) records strict container/JSON, sync/async timeout and response-selection regressions.
