# Maintain pinned SDK generators

Alice discovers that a generated client turns an omitted field into null. Preserve a failing behavioral scenario, identify the shared generator mapping and fix that capability before regenerating. Editing one emitted method would hide the defect until regeneration and repeat the work for later endpoints.

This reference owns common maintenance policy. The [Rust](../../inframeld-rust-sdk/references/generator-maintenance.md), [TypeScript](../../inframeld-typescript-sdk/references/usage-and-maintenance.md) and [Python](../../inframeld-python-sdk/references/usage-and-maintenance.md) references own language-specific behavior. The [Rust workspace](../../../../packages/sdk-tools/README.md), [Rust patch runbook](../../../../packages/sdk-tools/README.md#generation-inputs-and-patches) and [language qualification runbook](../../../../packages/sdk-tools/README.md) retain commands and cache mechanics.

## Establish the defect

Inspect the native OpenAPI operation, backend behavior and generated signature first. A backend contract defect belongs to its owner and needs authorized backend work. Do not alter a correct schema for a generator. Missing generation, a missing test binding and a broken fixture are different from a generator defect.

Qualify newly delivered operations and newly exercised schema/transport capabilities through [shared qualification](shared-qualification.md). Follow Coding Standards' scaffold-first TDD: expose only the missing test seam, observe the intended behavioral failure, then implement the smallest real fix. Import failures require the missing seam, not early implementation. Existing coverage can supply the regression when it already demonstrates the defect.

Use actual HTTP routers and shared FastAPI fixtures with controlled collaborators where applicable. Capability-only schemas remain synthetic. They cannot establish product jobs, receipts or other missing workflows. No real provider credentials or paid endpoints are needed for generator qualification.

## Patch the generator input

Read the affected tool's authoritative pins, configuration and ordered patch manifest. Verify source origin and archive/patch digests before applying changes. A checksum mismatch requires investigating bytes and provenance. It is not permission to recalculate a digest blindly.

Find the shared classifier, model mapping, client asset or built-in response template responsible for the behavior. Prefer the smallest coherent reusable fix with relevant positive and negative cases. Keep the source diff, ordered patch identity, digest and local revision where that tool defines one. Preserve upstream license notices. Upstream contributions, issues and pull requests are not required.

Apply patches to verified generator source or shipped resources before generation. Do not post-process emitted SDK source, add schema overlays or introduce another application HTTP client as an unreviewed workaround. Preserve caller-controlled base URLs/credentials, five-second buffered defaults, explicit timeout overrides, disabled automatic redirects/retries and the selected tracing policy. Read the affected language's override semantics before changing transport code.

## Regenerate and qualify

Use explicit generation through the [typed workflow](../../../../packages/sdk-tools/src/workflows/generate.ts). The [human walkthrough](../../../../packages/sdk-tools/docs/generators.md) locates concrete adapters and operating steps. Review generated signatures, models, serialization, dependency declarations and response behavior. Keep the native input unchanged for a generator-only fix. Retain changed generated source and lockfiles with the reviewed source inputs.

Compile and run clients independently. Keep generation, compilation, behavioral failures, drift and packaging failures distinct, and collect all selected results. Check clean-directory regeneration, dependency drift, applicable native model/type checks, behavioral scenarios, available generator tests and an external consumer build. Build costs exclude generation, installation and downloads. Published source-archive library tests are not an upstream integration suite that the archive does not contain.

For response-selection changes, retain each status/media schema through parsing and emitted native types. Check exact/class/default precedence, exact/wildcard representations, swapped schemas, nullable/bodyless alternatives and malformed containers. For metadata changes, qualify affected empty, buffered and live response paths, repeated headers and malformed bodies. Live-stream metadata must be obtainable before the whole body arrives. Preserve each language's qualified result modes. Do not repeat a request to recover discarded information. A requirement to test an affected path is not evidence that every SDK already supports it.

Ordinary SDK compilation must work without generator installation, source download or a running backend. Do not weaken a scenario or omit a failed SDK result to declare success. The consolidated runner reports every selected SDK independently. A failure in one cannot hide another result. Comparison baselines and their reproduction tooling are retired under ADR-0091.

## Upgrade or retire a patch

Upgrade deliberately rather than for every upstream release. Verify the new source origin/digest, update the version consistently, rebase remaining patches and inspect changed hashes, revisions and generated output. Run the same qualification and external-consumer checks as for a new fix, including the affected language's platform gate.

A patch that stops applying has not thereby become obsolete. Run its original regression against the proposed upstream implementation. Remove it only when that behavior passes without the local fix, retaining the test afterward. Surface changes to consumer signatures, response modes or failure behavior. Successful generation alone cannot establish safe adoption.

Reconsider the generator when a fix becomes a second serializer, needs broad analyzer/runtime redesign, introduces recurring endpoint-specific exceptions or causes repeated upgrade conflicts that obstruct feature work. Explain the measured cost and alternatives before expanding a maintained fork. No fixed patch-count threshold decides this, and a public HTTP escape hatch is not assumed.

## Diagnose the failing stage

| Failure | Action |
| --- | --- |
| Archive or patch digest mismatch | Stop preparation and inspect provenance and changed bytes. |
| Patch application fails | Inspect upstream changes, then rebase or prove a replacement fix against retained coverage. |
| Generated source fails compilation | Inspect models, signatures and dependencies separately from runtime behavior. |
| Wire behavior fails | Inspect the contract, fixture, native binding and generator without repairing observations in the driver. |
| Regeneration drifts | Inspect changed inputs/output and update artifacts only through authorized generation. |
| Standalone consumption fails | Inspect the distributable SDK boundary independently of backend or generator availability. |

Failed source verification stops that candidate before its SDK generation. Earlier fixture exports or other candidates may already have changed working files. Later failures can also leave output. Inspect the working tree, preserve unrelated work and report the actual stage rather than describing an unqualified update as successful.

Generator selection does not publish an SDK, implement the CLI or resolve [server-version compatibility](../../inframeld-application-contracts/references/decision-cli-server-compatibility.md). Do not dispatch remote CI merely to explain a question or edit guidance. Read dated reports for evidence and current source for mechanics.
