# Distinguish CLI command and background outcomes

CI admits a build and exits successfully, but the build can still fail later. The CLI must separate submission, inspection, waiting and uncertain outcomes. The [machine-output contract](cli-output-and-automation.md) defines common framing. The [logical recovery contract](operation-recovery-contracts.md) defines the backend facts it may present.

<a id="cli-outcomes-automation-and-change-presentation"></a>

CI submits an import and receives its durable acceptance. That command succeeded even though the job may fail later. Human and machine output must distinguish submission, inspection and completed work without repeating uncertain operations.

> **Status:** invocation outcomes, signals and bounded recovery hints accepted on 2026-10-29 through the approved joint #124/#156 specification plan. Runtime delivery remains pending. Existing Python types, generated OpenAPI and migrations own implemented backend shapes. Independent pending decisions are not accepted by this reference.

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

Do not reconstruct missing results or repeat model calls to populate a screen. No generic tracking schema is needed. The [logical job projection](operation-recovery-contracts.md#job-inspection) and Evaluation own typed facts and bounded reads. The CLI framing is accepted, while command-specific payloads and native backend delivery remain separate work. Mock counts and commands do not publish endpoints.

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
| Inspect original-request lookup successfully, with an unresolved retained match | `0` | Report the unresolved observation. This confirms neither admission nor absence of original effects and permits no resubmission. |
| Wait for the requested workflow. It fails or only partly completes | `1` | Preserve completed effects, unfinished/failed/uncertain work and owner-supplied reasons. Inspect original work. Resume only when the backend establishes eligibility. |
| Submission may have reached the server, but admission cannot be confirmed | `1` | Report uncertainty and only actually known recovery information. Find the original admission before repetition. Do not fabricate a job ID or a no-effect claim. |
| Required invocation inputs are missing or incompatible | `2` | Return a safe usage explanation without starting the requested work or prompting under `--no-input`. Generic confirmation cannot supply missing values or authority. |
| A wait expires before completion is known | `1` | Report last confirmed state and original identity. Wait expiry does not request cancellation or prove the backend stopped. |
| A descriptive dry-run completes | `0` | Success of the explanation only. Report checks performed, intended effects and unknowns. No execution, readiness, future permission or consent is established. |

These are the ordinary `0`/`1`/`2` meanings. [Interruption and detachment](#interruption-and-detachment) adds `130` for INT and `143` for TERM. JSON uses `succeeded` for `0`, `failed` for usage or known failure, `uncertain` for unestablished requested effects/completion and `interrupted` for signals. Known failure and uncertainty both ordinarily exit `1`. A valid answer that abstains can succeed. A tracing-only warning does not fail an otherwise successful query, but a separate trace-read command must report when its own request is denied or unavailable. Likewise, a ready build and a failed publication are separate facts. The automation contract must map every command variant before implementation.

<a id="cli-recovery-contract"></a>

## CLI Recovery Contract

The terminal and CI use the same saved backend operation. For a new command that changes state or can incur a charge, the CLI generates a request key unless automation supplies `--idempotency-key`.

A retry keeps the original target, account, project, command meaning and accepted inputs. If the acceptance response was lost, first look up the original operation. Changing the selected target or editing the Pipeline does not change what that retry means. [Local recovery hints](#minimal-local-recovery-hints) retain only enough original identity to request an authoritative lookup. They cannot prove what the server did or grant permission to continue.

[Interruption and detachment](#interruption-and-detachment) distinguishes Ctrl-C cancellation requests, `c` detachment and TERM. Preserve request, acknowledgment and confirmed job outcome as separate facts.

Commands requesting completion of durable work wait by default in interactive terminals and automation alike. `--json`, `--jsonl`, `--plain`, `--no-input`, piping and terminal detection do not change that default. `--no-wait` explicitly selects return after confirmed admission for commands that support durable admission. Inspection reads only the requested observation and never waits for the observed job to succeed unless waiting was explicitly requested. A wait timeout does not cancel work. Scripts must not encounter unexpected prompts. They receive separate command and job outcomes. Use the accepted machine framing and signal rules below. Exact HTTP transport delivery remains backend work. A terminal mockup does not publish an endpoint.

Configuration imports use these same durable jobs. They retain the approved definitions, destination mappings and completed resources. Continue only unfinished steps that the backend confirms are still safe and permitted. Changed inputs need a new review. An uncertain write must be resolved before it is repeated.

Query retries still return receipts rather than answer text, and one-time secrets retain their special recovery restrictions. If the backend's original history has expired, the CLI must not automatically create new paid work. The [logical recovery reference](operation-recovery-contracts.md) owns lookup, progress and continuation. Common output framing is accepted. Command-specific data and runtime qualification remain delivery work. It does not replace the implemented grant-idempotency behavior.

<a id="progress-presentation"></a>

<a id="show-useful-progress-in-plain-language"></a>

### Show useful progress in plain language

Alice evaluates 20 cases. Seventeen finish before the project spending limit prevents the next call. Tell her: "Evaluation stopped: project spending limit reached. 17 of 20 cases completed. Their results are saved." Identify the three not-started cases through Evaluation's protected results and offer inspection. Offer `job resume` only when the backend reports eligible remaining work. Admission still rechecks current authority, retained inputs and spending. Resolving the budget does not restart work automatically.

CLI progress and result presentation selects concise outcome/reason/next-action copy without removing counts or results. The initiating domain supplies meaningful units and saved outcomes. Shared job support supplies operation state and recovery eligibility. Do not add a universal per-item tracking framework or job states to fill a screen. [Evaluation](../../inframeld-evaluation/references/metrics-and-evidence.md#result-presentation) owns questions, scoring and case details.

- Show actual progress when known, with a named unit and denominator. Do not invent a percentage, time estimate, zero or successful result when information is unavailable. Preparation can show its current activity without a case count.
- Separate an answer being saved from its scoring being complete. Partial, failed, canceled, unattempted and uncertain work must remain distinguishable. A total or saved-result statement must come from authoritative retained observations, not elapsed time or local guesses.
- Use a short default summary and a bounded list of items needing attention. Link to ordinary inspection for the rest. Summaries, identifiers, questions and counts all remain subject to current access and erasure. Do not fetch every protected item merely to render progress.
- [Interruption and detachment](#interruption-and-detachment) owns `c`, INT, TERM and bounded cancellation acknowledgment. Progress may say "Requesting cancellation" locally, "Cancellation requested" only after acknowledgment and "Job canceled" only after confirmation.
- A lost CLI connection means the job **may** still be running, not that it certainly is. Look up the original operation before starting again. A model request with an unknown paid outcome instead requires review. Say that it may have been charged and was not retried when those facts are established. Ordinary resume cannot repeat that call.
- Human and JSON views expose the same authorized facts and recovery limits. Human progress goes to stderr when stdout carries JSON. No animations or interactive key handling in noninteractive output. Reading or watching results does not rerun work.

These are accepted presentation requirements, not implemented guarantees or a wire schema. The owning domain supplies exact backend outcomes. The CLI maps them to honest output. Both that mapping and its bounded cancellation/recovery behavior require qualification.

## Output framing and dry-run

[CLI automation](cli-output-and-automation.md) owns the accepted stdout/stderr, JSON/JSONL framing and descriptive dry-run contract. Command-specific fields remain with each feature. [Shared change views](cli-change-review.md#machine-change-views) preserve proposed, confirmed and stale meanings.

## Interruption and detachment

| Input or observation | Exit and effect |
| --- | --- |
| Interactive `c` while watching | Exit `0` for successful detachment. Report last permitted facts and that no cancellation was sent. Do not claim the backend certainly continues |
| First INT during an active durable-work wait | Return `130`. Stop normal polling, request cancellation under current authority and allow at most five seconds from receipt of INT for acknowledgment |
| First INT elsewhere | Return `130` without inventing a job or cancellation. A submission already dispatched can remain uncertain |
| Second INT | Return `130` immediately without further network work or waiting for the first cancellation request |
| TERM | Return `143`, stop local observation and send no implicit backend cancellation |
| Wait deadline expires | Return `1` without requesting cancellation. Preserve last permitted state and original references |

On first INT, immediately explain on stderr that interruption has started and that a second INT exits without waiting. Do this before credential access or network cleanup, with wording that distinguishes requesting cancellation from a recorded request. The five seconds includes credential access and cancellation dispatch, not five seconds per phase. Do not start interactive login or automatically retry an uncertain cancellation. A distinct cancellation mutation uses its own request identity against the original job. [Its backend contract](operation-recovery-contracts.md#cancellation) owns reconciliation and current authority. A canceled/succeeded/failed job discovered during interruption keeps that actual state while the invocation still reports interruption.

No interactive `c` handler runs under noninteractive input or `--no-input`. Acknowledgment confirms only the recorded request. Report unconfirmed delivery if it is denied, times out or loses contact. Signals cannot undo completed effects or recall an external call. Best-effort machine output uses `interrupted` with a safe local error and any permitted observation. Second INT, forced termination and broken stdout may prevent a final record.

Local lifecycle commands retain confirmed started/stopped/unknown effects under the same invocation meanings. INT does not imply a successful rollback of partial startup. TERM does not cancel durable jobs, and stopping the runtime preserves their saved work under [local lifecycle](cli-local-runtime.md#persistent-lifecycle-status-and-deliberate-reset).

## Minimal local recovery hints

A request key must survive the interval before acknowledgment if the CLI generated it. Before dispatching a remote product mutation or chargeable request with a CLI-generated key, durably save a current-user recovery hint. If saving fails, fail before dispatch. Ordinary product reads, dry-run and local lifecycle observations create no hint. Provider login/refresh keeps its separate credential-lifecycle contract.

Callers supplying `--idempotency-key` may use a stateless path with no hint. They must retain the original immutable context, expected authority guard and key themselves. This allows CI with read-only local state. An explicit key neither proves that a request is a retry nor permits a different target or payload to replace its original meaning.

| Hint component | Meaning and restriction |
| --- | --- |
| Target-binding reference | Immutable locally registered binding reference, not an alias or authority to rediscover a replacement |
| Installation and principal | Original permanent identities, checked against trusted target/account bindings during recovery |
| Scope | Original organization ID and Project ID where applicable |
| Method and route | Original canonical logical method/route, preserving its original meaning rather than today's default resolution |
| Request key | Original opaque non-secret idempotency identity, subject to the existing 128-character limit |
| Expected original authority | Family and action captured from the submitting operation before dispatch. An untrusted lookup mismatch guard, never a permission snapshot |
| Creation time | UTC time of local creation, not proof of server admission or server retention |
| Known references | Operation/job identities only when actually received. No guessed IDs |

The current-user location of a hint can identify it without another public resource ID. A hint contains no payload, credential, fingerprint, answer, cached result or permission snapshot. Use restricted current-user storage, owner-only files/directories, and treat loaded contents as untrusted input. A corrupted or modified hint cannot redirect credentials or select a new binding.

Fixed private bounds are 1,000 pending hints per current OS user, each at most 32 KiB of UTF-8 stored representation. The representation's implementation/versioning stays private. Do not silently evict unresolved hints. Saving an oversized hint or reaching the count bound fails new submissions requiring a hint before dispatch. Report how to recover or explicitly discard existing hints. These bounds add no user setting, database, daemon or global coordinator. Separate invocations must not overwrite one another's hints or exceed the count limit through a race, without serializing their backend jobs.

Remove a hint after confirmed admission/result has been handed back successfully, or after explicit user discard. A known job reference handed back after admission is sufficient handoff, not a claim of completed work. Keep the hint when server acknowledgment or output delivery is uncertain. Local expiry guesses, cache cleanup and an absent file cannot establish that the request did nothing.

Recovery is explicit. Load original binding and current credentials through normal target/account rules, then request [authoritative lookup](operation-recovery-contracts.md#original-request-lookup). No current alias or environment override can retarget it. Deleted/missing target bindings, changed installation/principal identities, invalid credentials and unavailable history produce safe failures without replacement discovery or automatic replay. A hint cannot construct managed-local trust or authorize continuation. Missing or invalid expected authority is a recovery-input failure. Do not reconstruct it from current grants or defaults. A changed guard cannot recover another retained binding or downgrade a fixed route. Future unknown resource targets need an owner-specific pre-search contract. The guard remains within the same hint size/count bounds. A later replay still needs the original inputs and server fingerprint checks, which the hint deliberately does not retain.

## Qualification scenarios

The matrix defines future behavioral evidence for the owning implementation issues. These are not application tests executed by the specification PR.

| Scenario | Expected invocation and observation |
| --- | --- |
| Completion command in a terminal, a pipe or `--no-input --json`, with no waiting override | All wait for the requested workflow. Actual failure returns `1`, independently of input/output mode |
| Confirmed admission with explicit no-wait | `0` / `succeeded`, original references, no claim of completion |
| Lost admission acknowledgment | `1` / `uncertain`, original recovery information, no new paid request |
| Expired history or failed lookup | Completed read-only lookup can succeed with unresolved data. Denial/unavailability fails the read. Neither establishes no original effects |
| Target alias, account, Project or payload changes | Preserve original identity, deny mismatches, require ordinary fingerprint/current-authority checks |
| Inspect a failed job | `0` / `succeeded` with actual failed state and permitted saved results |
| Wait for failed/partial work or wait timeout | `1`, confirmed partial facts retained, timeout sends no cancellation |
| Answers saved but scoring incomplete | Distinct owner counts and unknowns match human and JSON views |
| Cancellation races with completion or acknowledgment loss | Preserve actual terminal state and acknowledged versus unconfirmed request |
| `c`, INT, second INT and TERM | Detach `0`, interrupt `130`, immediate second INT, TERM `143`, only first INT during active wait requests cancellation |
| Noninteractive missing input or incompatible stdout modes | `2`, controlled failure, no operation, browser/editor or prompt |
| Malformed invocation with diagnostic dry-run intent | `2` / `failed`, `mode: dryRun` when an exact `--dry-run` precedes `--`, otherwise `execute`, no effects |
| Help with otherwise invalid arguments or conflicting output flags | Plain-text help, exit `0`, no requested operation |
| Successful dry-run of read, mutation or lifecycle action | `0`, `mode: dryRun`, only permitted metadata checks, no requested operation or hint |
| Hint storage denied, oversized or full | No generated-key submission. Explicit-key stateless path remains available |
| Hint modified, binding deleted or account changed | No credential forwarding or replacement-target recovery |
| Output fails after admission | No false success/no-effect claim, hint retained when handoff is uncertain |
| JSON/JSONL, terminal/plain, warning and change views | Same permitted effects/counts/unknowns, one result, correct channels and labels |

Runtime delivery belongs to #158 and the relevant CLI command/recovery issues. This contract supplies no new command registration, application implementation or permanent qualification harness.
