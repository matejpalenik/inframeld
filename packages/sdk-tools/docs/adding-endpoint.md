# Add endpoint coverage

Alice adds an optional nullable description to an endpoint. Three meaningful cases are omission, explicit null and a value. The backend must receive each intended input, and the client must expose the appropriate result or inspectable failure.

## Work from the backend outward

Deliver and test backend behavior first, then run `pnpm openapi` to update `contracts/openapi/v1/inframeld-v1.json`. Application Contracts owns HTTP meaning and domain workflows own business expectations. A new operation must have an `operationId` and shared success coverage. Changed fields also require scenario review even when the ID stays unchanged.

Open the nearest [feature test](../tests/conformance). [Consent](../tests/conformance/consent.ts) is a complete inspected example: its input sits beside the status, redirect and backend-body assertions. Tests use ordinary Node assertions, not a JSON expectation language or a separate assertion switch.

Register each case once through `sdkTest`, supplying its stable ID, operation and expected success/failure category. Keep assertions in that test body. Add a new feature module to [the explicit imports](../tests/conformance/index.ts) only when it represents a distinct area.

## Bind native SDK calls

Extend the [operation protocol](../src/conformance/protocol.ts) and each native driver's bindings. Drivers translate test input into generated models and operation parameters. They do not implement HTTP operations. Keep the call in the affected language's operation module and let compilation or invocation expose unsupported generated APIs.

| Driver | Concrete edit |
| --- | --- |
| Rust | Add the generated call in [operations.rs](../drivers/rust/src/operations.rs) and any exhaustive typed error conversion in [observation.rs](../drivers/rust/src/observation.rs), then its advertised ID to `BINDINGS` in [main.rs](../drivers/rust/src/main.rs). Review that entry point’s operation-specific credential/header arguments so a generated header parameter is not also sent as a default header. |
| TypeScript | Add a call in [typescript.ts](../drivers/typescript.ts). Its binding inventory derives from those keys. Node and Chromium use the same calls. |
| Python | Add the operation to the strict `Operation` literal in [protocol.py](../drivers/python/protocol.py). Add direct sync and async functions in [operations.py](../drivers/python/operations.py) and pair them once in `BINDINGS`. Both profiles use that inventory. |

If the endpoint introduces a router not yet included in the [controlled backend factory](../../../apps/backend/tests/support/sdk_conformance_app.py), include that production router with controlled collaborators. Existing witnessing records arbitrary JSON fields, so description cases need no field-specific observer. Keep fixture state isolated and real databases/providers outside this suite.

For JSON bodies, compare the independent witness to the intended input. Explicitly test omission/null differences. For multiple status/media bodies, test each legitimate alternative and reject swapped bodies. Keep nullable results distinct from body absence and narrow native TypeScript failures by kind. Check exact success status, typed failures and relevant headers/query/path encoding. Multipart cases compare actual uploaded bytes and filenames. A case must invoke its declared operation and dispatch each call once.

Declare `expectedCalls` when a case intentionally invokes more than one operation call. Use a sequence for client reuse, such as a decoding failure followed by a healthy call. The same case runs in every selected profile. Keep language-specific model/type and synthetic capability checks separate from shared HTTP counts.

## Regenerate and verify

Run `pnpm sdk:generate`, review source/dependency changes, then use a filtered `sdk:test` command while iterating. Finish with `pnpm sdk:verify`. Ordinary tests never regenerate source. Full verification requires every applicable profile and case, not only the edited test.

Even a filtered run first checks the whole production/fixture operation inventory for its selected profile. Missing unrelated coverage or bindings can therefore block the chosen case. Filtering narrows execution, not that coverage prerequisite.

A failure can mean stale source, a missing binding, an incorrect test/backend expectation or a generator defect. Inspect the witness and native error first. For a generator defect, retain the failing regression and follow [generator maintenance](generators.md). Do not alter correct OpenAPI or repair the result in a driver.

The controlled backend proves HTTP/client behavior. Persistence, real providers and complete product journeys retain their own test layers. Read the [architecture map](architecture.md) when changing fixture or driver mechanics.
