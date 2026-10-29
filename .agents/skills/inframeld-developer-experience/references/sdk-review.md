# Review the generated SDK journey

Alice wants to call a delivered operation from Python, TypeScript or Rust. The useful journey includes installation, client construction, credential handling, the returned type and recovery. An endpoint's presence in generated code does not prove that a developer can use it correctly from the guide.

Read the affected language owner: [Python SDK](../../inframeld-python-sdk/SKILL.md), [TypeScript SDK](../../inframeld-typescript-sdk/SKILL.md) or [Rust SDK](../../inframeld-rust-sdk/SKILL.md). Read [shared qualification](../../inframeld-sdks/references/shared-qualification.md) when reviewing cross-language behavior, conformance coverage or generation changes. Do not require loading every SDK skill for one consumption example.

## Use the actual public API

Inspect the generated operation, request and response types, client construction and lifecycle. Verify exact argument names, optionality, enums, unions and error paths against native OpenAPI and inspected generated code. Keep server contract problems, generator problems and example problems distinct. Fix an owning generator or contract when that is the cause, rather than editing generated files by hand.

A complete first-use example names its file, includes imports, builds the supported client, reads credentials safely and closes owned resources when required. The TypeScript example must use the delivered Fetch/Zod behavior. The Python example must use the delivered HTTPX/Pydantic behavior. Rust examples must use the selected generator's real enum and client API. Do not smooth over differences with a second handwritten application client.

Check repository-local installation honestly. A generated package that has not been published needs an accurate local build or dependency path. A familiar registry command is misleading if the package is unavailable. A sample can be excellent without implying that production packaging is already delivered.

## Follow normal and uncertain results

Inspect one successful result and the failure that affects the next decision. Check HTTP errors, decoding failures, validation failures and product outcomes separately. An observation operation can succeed while reporting an unresolved original action. The consuming code must not treat successful transport as proof of a successful write.

Check unknown discriminator and enum behavior according to the accepted SDK compatibility policy. Do not claim that a generic fallback preserves fields when the generator drops them. Inspect how nullable and omitted values are represented. In examples, handle the actual generated wrapper, enum or union. A fake helper such as `result.is_success()` is not an acceptable shortcut unless it is a real delivered API.

Keep current credentials and retained original context separate. Reconstructing a write from today's default account can change meaning. A timeout does not establish no effects. SDK or documentation retry advice must preserve the accepted idempotency and authority rules, and must not trigger paid calls implicitly.

## Compare languages at the behavioral boundary

Equivalent examples should describe the same task, identities, route, current permission requirements and returned meaning. They need not have identical syntax or an artificial shared abstraction. Native idioms can make each language easier to use while preserving the same contract.

Check controlled fixture coverage for serialization, supported response variants, problem details and unknown values where required. Name whether a check used a fixture or a real local server. A unit fixture cannot establish database or provider qualification. A passing generator build cannot establish all operation coverage.

Consider how a developer diagnoses a problem. Preserve useful request or operation identifiers without leaking credentials. Messages should distinguish invalid local input from a rejected request, an unavailable transport and an unknown remote outcome where the contract supports that distinction. Avoid catching everything and reporting a false success or an empty result.

## Keep remedies proportionate

The smallest useful remedy may be a corrected example, an actionable error, a generator patch or an exact response schema change. Do not introduce a new facade merely to hide one awkward generated name. Explain the affected user task and maintenance cost before proposing a wrapper, configuration system or extension mechanism.

Report the actual base/head, affected language and operation, source locations, execution evidence and remaining limits. Use Review's priorities and readiness. A defect in one language does not imply all three fail, and a clean narrow review is not full cross-language qualification.
