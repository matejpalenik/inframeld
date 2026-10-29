# CLI outcomes, automation and change presentation

Alice scripts a command that admits work, then inspects its outcome. One machine result must describe the same permitted facts as the human view, including uncertainty and partial saved effects.

> **Status:** common CLI representation accepted on 2026-10-29 through the approved joint #124/#156 specification plan. Runtime implementation and command-specific data models remain delivery work. The executable currently exposes offline help/version. No JSON flag, job command or output example below is a claim of an executable feature.

## Read the right contract

[Invocation outcomes](cli-result-contracts.md) owns exits, interruption and recovery hints. [Logical recovery contracts](operation-recovery-contracts.md) owns backend facts and authority. This reference owns machine framing, channels and descriptive dry-run. [Change reviews](cli-change-review.md) owns typed Current/Proposed, Before/Now and Reviewed/Now meaning. [Presentation components](cli-presentation-components.md) owns reusable rendering mechanics.

<a id="use-one-predictable-machine-channel"></a>

## Use one predictable machine channel

Ordinary `--json` emits exactly one final, pretty-printed UTF-8 JSON object followed by a newline on stdout, including controlled failures. Whitespace is not a compatibility contract. Human diagnostics/progress go to stderr. No preliminary admission object precedes the final object. `--json` and `--jsonl` are mutually exclusive and conflicting modes are usage errors before operation dispatch.

For controlled argument failures, use this diagnostic precedence before full command execution:

1. An exact `-h` or `--help` before the first standalone `--` selects plain-text help and exit `0`, despite other argument errors or output-mode conflicts. Use the available command help through clap. Tokens after the delimiter are positional input, not help requests.
2. Otherwise, recognize exact `--json` and `--jsonl` tokens before that delimiter as diagnostic output intent. A JSONL-intent parsing failure emits its single final result record. Both output modes together select one ordinary JSON failure object with exit `2`.
3. For the failed invocation's required `mode`, an exact `--dry-run` before the delimiter selects `dryRun`, otherwise use `execute`. Ignore embedded values such as `--name=--dry-run` and all tokens after the delimiter. This is diagnostic intent only, not a successful parse or execution claim.

This narrow check neither parses command values nor resolves context. Valid invocations use clap's actual parsed options. Reviewed diagnostics never echo arbitrary argument values. Clap's successfully recognized short-version output retains its offline plain-text exception.

These argument fragments belong to this reference's failed-parsing contract. They describe future behavior, not invocations supported by today's executable:

| Argument fragment before a controlled usage failure | Diagnostic stdout | Envelope mode | Exit |
| --- | --- | --- | --- |
| `--json --dry-run --unknown` | One JSON object | `dryRun` | `2` |
| `--jsonl --dry-run --unknown` | One final JSONL result record | `dryRun` | `2` |
| `--json -- --dry-run` | One JSON object | `execute` | `2` |
| `--json --name=--dry-run --unknown` | One JSON object | `execute` | `2` |
| `--json --jsonl --dry-run` | One JSON object | `dryRun` | `2` |
| `--json --jsonl --help` | Plain-text help | No envelope | `0` |

Every ordinary object contains these six fields:

| Field | Accepted version 1 representation |
| --- | --- |
| `schemaVersion` | Strict integer `1` |
| `mode` | `execute` or `dryRun`. Describes what this invocation requested |
| `outcome` | `succeeded`, `failed`, `uncertain` or `interrupted`. Describes the invocation, not a new job state |
| `data` | A command-specific typed object, or `null` if no permitted result data is available |
| `error` | One of the source-specific error objects below, or `null` for a successful invocation |
| `warnings` | Array of structured warning objects, empty when none exist |

Failed, uncertain and interrupted results have a non-null error. Successful results have `error: null`. `data` can retain confirmed partial effects or the last permitted observation under any outcome. Do not infer an empty result or no effects from `data: null`. A command's data definition supplies its typed identities, recovery references and counts rather than serializing human rows or arbitrary debug values.

An uncertain outcome means requested effects or completion cannot be established. A failed inspection with no new effects is `failed`, not a claim that the observed job failed. Missing arguments use `failed` with exit `2`. Interrupted invocations use `interrupted` even when their data retains uncertain remote effects. [The exit table](cli-result-contracts.md#separate-command-success-from-background-work-success) owns the mapping.

In this reference's `use-one-predictable-machine-channel` section, the following is an illustrative `data` payload inside the accepted envelope. Its leaf field names are not a published job wire model. Inspection succeeded even though the observed job failed:

```json
{
  "schemaVersion": 1,
  "mode": "execute",
  "outcome": "succeeded",
  "data": {
    "operationId": "operation-example-42",
    "state": "failed"
  },
  "error": null,
  "warnings": []
}
```

The following example in this reference's failed-parsing contract reports requested dry-run intent even though argument validation failed. The local code is illustrative. No input, context or requested operation was executed:

```json
{
  "schemaVersion": 1,
  "mode": "dryRun",
  "outcome": "failed",
  "data": null,
  "error": {
    "source": "cli",
    "code": "invalid_arguments",
    "message": "Check the supplied arguments and use --help for usage."
  },
  "warnings": []
}
```

### Preserve error source and safe content

A local error has exactly `source: "cli"`, `code` and `message`. The code is a stable lowercase identifier matching `^[a-z][a-z0-9_]*$`, at most 64 characters. The message is reviewed safe text of 1-512 characters, never arbitrary exception text or the submitted value. Feature implementations register their specific local codes with their owning command contract before exposing them.

Controlled failures also write a concise human explanation to stderr. The machine result stays on stdout, with no duplicate JSON diagnostic dump.

A backend error has `source: "backend"` and `problem`, preserving the [existing Problem Details](http-problem-contract.md#http-representation) body and its meaning. Preserve recognized safe extension members such as an original operation reference. Do not fabricate status, request ID or a backend problem when transport failed without a response. Do not serialize arbitrary vendor bodies as problems.

Warnings use `code` and `message` with the same identifier/text bounds. They do not convert a failed operation into success. Bound warning lists with the owning command's result, and expose unavailable additional detail honestly through its normal inspection contract. Domain-specific codes and data remain typed command contracts, not a generic string-valued result map.

The next two examples belong to this reference's error-source contract. They show a local failure and an established backend denial respectively:

```json
{
  "schemaVersion": 1,
  "mode": "execute",
  "outcome": "failed",
  "data": null,
  "error": {
    "source": "cli",
    "code": "missing_input",
    "message": "Provide the required target selection."
  },
  "warnings": []
}
```

```json
{
  "schemaVersion": 1,
  "mode": "execute",
  "outcome": "failed",
  "data": null,
  "error": {
    "source": "backend",
    "problem": {
      "type": "about:blank",
      "title": "Forbidden",
      "status": 403,
      "detail": "The operation is not permitted.",
      "code": "http_error",
      "requestId": "97575c8b-e8f8-4ce7-84d7-2cb2ff4e143a"
    }
  },
  "warnings": []
}
```

These messages and the illustrative `missing_input` code explain the shape. Command-specific vocabularies and the server's reviewed catalogue retain their own definitions. Do not copy an example message into a competing HTTP catalogue.

### Versioning and explicit streaming

Consumers ignore additive fields and tolerate unfamiliar diagnostic codes and backend problem extensions. These compatibility rules apply to ordinary result objects, both JSONL record types and the ordinary result nested in a final record. Breaking changes to required fields, types or outcome meaning require a new `schemaVersion`. Ignoring additive fields never permits missing or malformed required fields or an unsupported schema version. Reject such records or results instead of interpreting them as success. These rules do not promise that unimplemented command data schemas already exist.

Explicit `--jsonl` emits newline-delimited UTF-8 objects in observed order. A progress record requires `schemaVersion: 1`, `type: "progress"` and `data`, a typed permitted observation. The final record requires `schemaVersion: 1`, `type: "result"` and `result`, the ordinary result object with its six required fields. There is at most one final record and no later progress. Normal controlled completion emits that final record even when there were no progress records.

This reference's JSONL example has one observation and a final successful inspection result. Its progress/data fields remain illustrative command payloads:

```jsonl
{"schemaVersion":1,"type":"progress","data":{"state":"running"}}
{"schemaVersion":1,"type":"result","result":{"schemaVersion":1,"mode":"execute","outcome":"succeeded","data":{"state":"failed"},"error":null,"warnings":[]}}
```

`watch` never silently selects JSONL. Watch uses ordinary current-authority polling, respects backend pacing such as `Retry-After` and keeps requests bounded under the command's transport policy. Observations can skip intermediate states. No server stream, durable event ID, replay cursor, independent presenter poller or event history is required.

### Channels, exceptions and input

For human record-oriented text, `--plain` disables decorative styling and layout wrapping, keeping each record on one physical line. Escape embedded line/control characters rather than losing permitted values. Keep field headings and change meaning explicit. This text-only flag leaves JSON/JSONL unchanged and does not alter interaction, waiting or pagination. Complex structured values remain available through the typed JSON result, without a universal flattening format.

Help and clap's short-version flags remain plain-text, offline exceptions. Help has the precedence defined above. They short-circuit product execution. An explicit version command's future machine representation uses its approved typed data without remote verification. Raw exports, shell completions and show-once secret delivery keep their dedicated channels. Reject competing stdout consumers before execution rather than mixing artifact bytes or a secret into the envelope.

Output format does not select identity or interaction. Noninteractive input or `--no-input` disables prompts and interactive key handling. Missing required values fail without implicit login, browser/editor launch or guessed choices. A generic `--yes` cannot supply a value, authority or approval for additional paid effects. A supported explicitly requested login/export flow keeps its own input/channel contract.

Evaluate styling per output stream. Disable it for a non-terminal destination, nonempty `NO_COLOR`, `--no-color` or `TERM=dumb`. Disable animations when stdout is not a terminal or input is noninteractive. JSON/JSONL contains no ANSI styling. Quiet mode may suppress human progress, never the promised machine result or failure meaning. Unknown permitted values remain explicit unknowns in typed data. Omit forbidden facts and retain current authority for identifiers, warnings and counts as well as effects.

When a lost server response leaves requested effects or workflow completion unestablished, report a controlled uncertain outcome if the process and stdout remain usable. A failed read-only observation keeps its failed-inspection meaning. A killed process, second interrupt or broken stdout may leave no complete final object. Never emit a replacement success after output failure. Silence or incomplete output proves neither success nor absence of remote effects.

<a id="keep-automation-and-dry-run-within-ordinary-authority"></a>

## Keep automation and dry-run within ordinary authority

Automation preserves explicit target/account/project precedence and [original-operation recovery](operation-recovery-contracts.md). A nonzero exit, absent final record or recoverable error label never authorizes a new key, paid request or newer revision. The CLI translates ordinary backend capabilities rather than implementing another workflow engine.

<a id="cli-dry-run"></a>

<a id="explain-an-invocation-without-performing-its-operation"></a>

## Explain an invocation without performing its operation

Every command supports descriptive `--dry-run`, including reads and local lifecycle operations. Help explains a command generally. Dry-run explains these inputs and effective context. Reading a list's dry-run describes the scope/page without fetching it. Diagnose describes its check set without running it. Build explains preparation/publication policy without admitting a job or acquiring release authority.

The envelope has `mode: "dryRun"`. Its typed command data identifies intended destinations, outgoing data categories and effects, the checks actually performed and unresolved choices. A checked fact has an authoritative observation. Cached or unknown facts are labeled accordingly. The exact command-specific fields remain with that feature rather than a universal planning document tree.

Necessary bounded, normally authorized metadata reads are permitted. They can refresh credentials for the same identity and produce backend request logs. Do not promise zero network activity or literally zero infrastructure writes. Never start interactive login, perform the requested product read, issue credentials, create recovery hints, admit/resume jobs, reserve spending, upload, call models, run synthetic provider tests, prepare indexes, build, publish, back up, reset or start/stop services.

Same-identity refresh is a narrow metadata-access exception, not permission to execute a requested login/issuance command. Inspect local input only within explicit scope and bounds, without an undisclosed filesystem scan or protected-content/secret disclosure. Invalid inputs still fail. Inaccessible metadata cannot appear as verified plan data.

A successful explanation exits `0` without establishing execution, readiness, future permission, consent or a reserved revision. Removing the flag still requires normal admission and current authority. Reuse ordinary parsing, context and authorized metadata instead of duplicating policy in a planning engine. [Change presentation](cli-change-review.md#machine-change-views) owns typed proposed versus observed values.

## Qualification and delivery

Backend logical facts are accepted separately from delivered models/OpenAPI. Common framing is accepted separately from each command's typed data. Native FastAPI/OpenAPI and generated clients remain the delivered HTTP authority. Add no handwritten application client or competing schema artifact for this specification.

Downstream checks must cover one final JSON object, valid JSONL ordering, local/backend error source, partial data on failure, warnings, missing input, output conflicts, interrupted output, dry-run effects and human/JSON parity. Check additive fields in ordinary results, progress records, final records and nested results. Missing or malformed required fields and unsupported schema versions must still be rejected. [The combined scenario matrix](cli-result-contracts.md#qualification-scenarios) owns cross-boundary cases. These are requirements, not application tests run by this documentation change.

## Follow clig.dev and record product exceptions

Use [clig.dev](https://clig.dev/) as the default CLI UX guidance. Any proposed departure needs a concrete reason and developer resolution in the owning contract. The [help](https://clig.dev/#help), [output](https://clig.dev/#output), [interactivity](https://clig.dev/#interactivity) and [signal](https://clig.dev/#signals-and-control-characters) guidance informs the rules above. The envelope, default waiting and universal descriptive dry-run are Inframeld choices, not requirements imposed by that guide.

**Approved exception, reconfirmed on 2026-10-29:** [generic rerun-to-recover advice](https://clig.dev/#robustness) cannot authorize another potentially paid or uncertain operation. Preserve the original request and perform explicit lookup before eligible replay/continuation. The developer explicitly retained this boundary after comparing the guide. Recoverability does not require automatic resubmission.

[Target context](cli-targets-and-accounts.md#cli-context) remains independent of working directory, and [discovery transport](cli-targets-and-accounts.md#implemented-discovery-profile) uses explicit proxy choices. Those existing trust decisions constrain the guide's conditional configuration/environment suggestions. They are not a general ban on ordinary supported environment settings and are not reopened by this UX alignment. Runtime delivery and qualification remain separate.
