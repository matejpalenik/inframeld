# Distinguish CLI command and background outcomes

CI admits a build and exits successfully, but the build can still fail later. The CLI must separate submission, inspection, waiting and uncertain outcomes. Exact missing framing fields remain pending rather than being guessed here.

<a id="cli-outcomes-automation-and-change-presentation"></a>

CI submits an import and receives its durable acceptance. That command succeeded even though the job may fail later. Human and machine output must distinguish submission, inspection and completed work without repeating uncertain operations.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="keep-cli-and-portability-contracts-explicit"></a>

### Keep CLI and portability contracts explicit

[The Access contract reference](../../inframeld-access-models/references/actions-and-initial-grants.md) records accepted identifiers, exact targets/principal eligibility, fixed creator assignments, human-only resource provisioning, invitations and semantic operation inputs/results/revisions. Every protected operation must declare credential families. Preserve existing session route/operation/schema names. Eligible application updates use their own context, while creation and other human-only operations reject application principals. The reference also captures [new bounded Access mutations](../../inframeld-access-models/references/grant-contracts.md#mutation-profile), [grant management](../../inframeld-access-models/references/grant-administration.md#grant-management), key replay and private recovery/maintenance inputs. These contracts are accepted design, not implemented DTOs or generated JSON/OpenAPI schemas. The [complete Access HTTP draft](../../inframeld-access-models/references/grant-contracts.md#http-operation-matrix) now gives the new operation/schema matrix. [Maintenance](../../inframeld-access-models/references/host-maintenance.md#maintenance-wire) and [private recovery](../../inframeld-access-models/references/private-recovery-handoff.md#recovery-wire) give the proof/evidence handoff for their owning implementation and qualification review. Downstream owners retain full domain schemas and runtime qualification.

Every CLI workflow must support automation. Ordinary JSON mode returns one final, versioned result. JSONL streaming must be explicitly selected. Human progress goes to stderr, commands use the documented exit codes, and scripts encounter no surprise prompts.

The command result is distinct from the job or resource state. Preserve the meaning of backend Problem Details, while clearly identifying validation errors that occurred locally in the CLI. Do not create a competing HTTP error wrapper. Secrets and downloadable artifacts use separate channels.

Every command, including reads, supports a descriptive dry-run without performing the requested operation. A dry-run reserves nothing and does not guarantee that execution will still be authorized later.

Use plain wording without hiding information. Show confirmed progress, saved results, counts and denominators. Include a bounded list of cases needing attention, with ordinary inspection for full detail. [Jobs](#progress-presentation) owns cancellation and recovery. [Evaluation](../../inframeld-evaluation/references/metrics-and-evidence.md#result-presentation) owns answer, score and case-result details. JSON exposes the same permitted facts through fields, not text scraped from the screen.

Keep these distinctions visible:

- Unknown progress is not zero progress.
- Acknowledging a cancellation request is not confirming cancellation.
- Successfully reading a job does not mean the job succeeded.
- Losing contact with the backend is different from not knowing whether a provider completed a paid call.

Do not reconstruct missing results or repeat model calls to populate a screen. No generic tracking schema is needed. The job, Evaluation and automation contracts must define typed outcomes and bounded reads before generated clients consume them. Mock counts and commands do not publish fields or endpoints.

Configuration portability adds offline TOML validation, coherent authorized exports, destination-aware read-only review and durable application-owned imports. [Its guide](configuration-export-and-import.md) defines scope and effects. Exact schemas/defaults/equivalence and resource permissions are explicit prerequisites. Evaluation owns optional protected JSONL dataset transfer. No generated client or Rust command may invent missing wire fields, permission identifiers or a client-side bypass of domain guards.

The [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md) separates common client/output contracts, Access dispatch/capabilities, model metadata, direct-query admission, Evaluation proof, tracing and portability specification from implementation. Adapters translate reviewed application contracts, not terminal mockup text. None of these additions broadens the two-tool MCP surface.

<a id="cli-automation-outcomes"></a>

<a id="separate-command-success-from-background-work-success"></a>

### Separate command success from background-work success

CI starts an import without waiting. The backend accepts and saves the work, so that command succeeds. Later, CI reads the job and learns that a Pipeline update failed after two resources were created. The read also succeeded, but the import did not complete. A command waiting for the complete import must report non-success.

The CLI automation outcome contract must represent these differences using the existing backend status system.

For each invocation, distinguish **what the caller requested**, **the command's outcome**, **confirmed backend state/effects** and **what is safe to do next**. An exit code answers the first two, not every business question inside the result. Inspecting a failed job is useful successful work. Waiting for that same failed workflow is not successful completion.

| Requested action and confirmed observation | Ordinary exit result | Facts and safe next action |
| --- | --- | --- |
| Admit work with `--no-wait`. Durable admission and required local transfer are confirmed | `0` | Return known original job/operation identity. Admission is not completion, current progress or publication. Read/watch separately if needed. |
| Inspect an existing failed job successfully | `0` | Return its actual failed state and permitted saved/unfinished results. Inspection neither retries nor rewrites that state. |
| Wait for the requested workflow. It fails or only partly completes | `1` | Preserve completed effects, unfinished/failed/uncertain work and owner-supplied reasons. Inspect original work. Resume only when the backend establishes eligibility. |
| Submission may have reached the server, but admission cannot be confirmed | `1` | Report uncertainty and only actually known recovery information. Find the original admission before repetition. Do not fabricate a job ID or a no-effect claim. |
| Required invocation inputs are missing or incompatible | `2` | Return a safe usage explanation without starting the requested work or prompting under `--no-input`. Generic confirmation cannot supply missing values or authority. |
| A wait expires before completion is known | `1` | Report last confirmed state and original identity. Wait expiry does not request cancellation or prove the backend stopped. |
| A descriptive dry-run completes | `0` | Success of the explanation only. Report checks performed, intended effects and unknowns. No execution, readiness, future permission or consent is established. |

These are the ordinary `0`/`1`/`2` meanings. They do not assign signal codes or provide every domain-specific mapping. A valid answer that abstains can succeed. A tracing-only warning does not fail an otherwise successful query, but a separate trace-read command must report when its own request is denied or unavailable. Likewise, a ready build and a failed publication are separate facts. The automation contract must map every command variant before implementation.

<a id="cli-recovery-contract"></a>

## CLI Recovery Contract

The terminal and CI use the same saved backend operation. For a new command that changes state or can incur a charge, the CLI generates a request key unless automation supplies `--idempotency-key`.

A retry keeps the original target, account, project, command meaning and accepted inputs. If the acceptance response was lost, first look up the original operation. Changing the selected target or editing the Pipeline does not change what that retry means. Local recovery hints can help locate an operation, but cannot prove what the server did or grant permission to continue.

`Ctrl-C` requests cancellation. Pressing `c` stops watching and returns to the shell without canceling backend work. Report whether cancellation was merely requested or actually completed.

Human commands wait by default. The caller can explicitly choose to return after the backend accepts work, and a wait timeout does not cancel that work. Scripts must not encounter unexpected prompts. They receive separate command and job outcomes. Exact transport, output and signal contracts still need specification. A terminal mockup does not define them.

Configuration imports use these same durable jobs. They retain the approved definitions, destination mappings and completed resources. Continue only unfinished steps that the backend confirms are still safe and permitted. Changed inputs need a new review. An uncertain write must be resolved before it is repeated.

Query retries still return receipts rather than answer text, and one-time secrets retain their special recovery restrictions. If the backend's original history has expired, the CLI must not automatically create new paid work. The shared job contract owns lookup, progress and continuation. Output schemas and qualification remain explicit work. It does not replace the implemented grant-idempotency behavior.

<a id="progress-presentation"></a>

<a id="show-useful-progress-in-plain-language"></a>

### Show useful progress in plain language

Alice evaluates 20 cases. Seventeen finish before the project spending limit prevents the next call. Tell her: "Evaluation stopped: project spending limit reached. 17 of 20 cases completed. Their results are saved." Identify the three not-started cases through Evaluation's protected results and offer inspection. Offer `job resume` only when the backend reports eligible remaining work. Admission still rechecks current authority, retained inputs and spending. Resolving the budget does not restart work automatically.

CLI progress and result presentation selects concise outcome/reason/next-action copy without removing counts or results. The initiating domain supplies meaningful units and saved outcomes. Shared job support supplies operation state and recovery eligibility. Do not add a universal per-item tracking framework or job states to fill a screen. [Evaluation](../../inframeld-evaluation/references/metrics-and-evidence.md#result-presentation) owns questions, scoring and case details.

- Show actual progress when known, with a named unit and denominator. Do not invent a percentage, time estimate, zero or successful result when information is unavailable. Preparation can show its current activity without a case count.
- Separate an answer being saved from its scoring being complete. Partial, failed, canceled, unattempted and uncertain work must remain distinguishable. A total or saved-result statement must come from authoritative retained observations, not elapsed time or local guesses.
- Use a short default summary and a bounded list of items needing attention. Link to ordinary inspection for the rest. Summaries, identifiers, questions and counts all remain subject to current access and erasure. Do not fetch every protected item merely to render progress.
- `c` stops watching without sending cancellation and returns to the shell. It does not close the user's terminal. Ctrl-C requests cancellation. Acknowledge locally that cancellation is being requested, but report "Cancellation requested" only after server acknowledgment and "Job canceled" only after confirmation. If acknowledgment is lost, report it as unconfirmed and offer status lookup.
- A lost CLI connection means the job **may** still be running, not that it certainly is. Look up the original operation before starting again. A model request with an unknown paid outcome instead requires review. Say that it may have been charged and was not retried when those facts are established. Ordinary resume cannot repeat that call.
- Human and JSON views expose the same authorized facts and recovery limits. Human progress goes to stderr when stdout carries JSON. No animations or interactive key handling in noninteractive output. Reading or watching results does not rerun work.

These are accepted presentation requirements, not implemented guarantees or a wire schema. The owning domain supplies exact backend outcomes. The CLI maps them to honest output. Both that mapping and its bounded cancellation/recovery behavior require qualification.

## Output framing and dry-run

[CLI automation](cli-output-and-automation.md) owns stdout/stderr, JSON framing and descriptive dry-run. These outcomes do not define missing exact machine fields.
