# CLI outcomes, automation and change presentation

Alice scripts a command that emits JSON and later reviews a proposed change. Automation needs predictable channels and explicit inputs. A dry-run explains this invocation without performing its requested operation. Job outcomes and visual review have separate detailed owners.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="use-one-predictable-machine-channel"></a>

#### Use one predictable machine channel

Ordinary `--json` emits one final versioned object on stdout, including controlled failures. Human diagnostics/progress go to stderr, not into that object stream. Do not emit a preliminary admission object followed by a second final object in the same ordinary invocation. Explicit JSONL streaming has separately specified framing, event order and completion semantics. `watch` alone cannot silently change framing.

Report a lost server response as a controlled uncertain outcome when the process and stdout remain usable. A killed process or broken stdout may leave no complete final object, so automation must handle incomplete output rather than interpret silence as success or no effects.

The following is **illustrative mock JSON, not a published schema**. The command successfully inspected a failed job:

```json
{
  "schemaVersion": 1,
  "outcome": "succeeded",
  "data": {
    "jobId": "job_import_42",
    "state": "failed"
  },
  "error": null
}
```

Scripts consume reviewed machine fields rather than parsing human copy, colors or raw vendor responses. Preserve backend Problem Details meaning and distinguish CLI-local errors without fabricating an HTTP status or server request ID. Keep secrets/show-once delivery and TOML/dataset artifacts out of ordinary result payloads. Reject conflicting stdout consumers before execution. Current authorization applies to identifiers, counts, context and detail as well as effects. The final fields, error vocabulary, optionality, schema evolution and platform signal handling remain deliverables, not fields selected by these mockups.

<a id="keep-automation-and-dry-run-within-ordinary-authority"></a>

#### Keep automation and dry-run within ordinary authority

No prompts, implicit login or fallback identity may repair missing input/authority in a noninteractive invocation. Every required choice has an explicit supported input, but `--yes` is neither a value nor a grant. Preserve explicit target/account/project precedence and one-shot overrides without changing saved selections. Current domain checks still govern each operation, even when a script or agent invokes it.

Dry-run describes the supplied command without performing its requested operation, including when that operation is a read. It may make only the necessary, bounded metadata reads that the caller is normally allowed to make. Those reads can refresh credentials for the same identity and produce backend request logs. Do not promise zero network activity or infrastructure writes.

Dry-run cannot fetch the requested list pages, run diagnostics, call models, admit or resume jobs, reserve spending, issue credentials, create recovery state for the proposed change or perform local lifecycle changes. Report checks that could not be completed rather than inventing success. Removing the flag still requires the normal inputs, consent, permissions and reviewed-state checks.

[Original-operation recovery](jobs-and-recovery.md#automation-recovery) preserves the same context, inputs and request identity. A nonzero exit or recoverable error label is not permission to generate a new idempotency key, rerun uncertain paid work or accept a newer revision. The CLI translates ordinary backend capabilities rather than implementing another workflow engine.

The [clig.dev basics](https://clig.dev/#the-basics), [output](https://clig.dev/#output) and [interactivity](https://clig.dev/#interactivity) guidance support structured output, stream separation and explicit noninteractive inputs. Inframeld's envelope, universal descriptive dry-run and exact outcome meanings remain product decisions, not clig.dev certification or tested guarantees. The CLI contract must define shared behavior and durable-work presentation, then qualify them with actual exit, output, saved-state and call evidence.

<a id="cli-dry-run"></a>

<a id="explain-an-invocation-without-performing-its-operation"></a>

### Explain an invocation without performing its operation

Every command supports descriptive `--dry-run`, including reads. Help describes a command generally. Dry-run describes these supplied inputs and effective context. `pipeline list --dry-run` describes the scope/page without fetching that page. A query plan does not infer. Build explains preparation/publication policy without creating a job/version or release authority. Diagnose explains its check set without running the diagnostic suite. Local commands explain rather than change settings or runtime state.

Necessary bounded, normally authorized metadata reads are permitted. They can involve same-identity credential refresh and backend request logging, so do not promise zero network activity or literally zero infrastructure writes. Never start interactive login. Label verified observations, cached information and unknowns separately, and state which metadata checks actually ran.

Dry-run never uploads, performs hosted or local inference, sends synthetic provider tests, creates jobs/reservations, issues credentials, invites users, starts/stops services, backs up/resets data, prepares indexes, builds or publishes. Same-identity refresh is a narrow metadata-access exception, not permission to execute a requested login/issuance command. Inspect local input only within explicit scope and bounds, without an undisclosed filesystem scan or protected-content/secret disclosure.

Explain known destinations, outgoing data categories, charges, effects and unresolved choices. Invalid inputs still fail. Inaccessible metadata cannot appear in a plan. Noninteractive missing input is an error, not a guessed selection. JSON carries equivalent safe meaning. Reuse normal parsing/context and backend metadata capabilities rather than duplicating release/access/accounting policy in a second CLI planning engine.

Removing the flag does not approve execution or reserve the reviewed state. Actual admission still needs consent, current authority, budget and revision guards. A later configuration or policy change conflicts normally. The CLI output contract still needs exact response schemas, metadata bounds, protected-input handling and behavioral coverage. No generic planning service or new public endpoint is selected.

## Inspect outcomes or review changes

Use [CLI result contracts](cli-result-contracts.md) for admission versus completion, structured outcomes, bounded status, waiting, cancellation and uncertainty. Use [change review](cli-change-review.md) for current/proposed and before/after presentation. Neither display grants authority or repeats remote work.
