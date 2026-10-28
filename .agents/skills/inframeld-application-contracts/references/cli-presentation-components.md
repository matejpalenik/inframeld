# Share CLI presentation mechanics without changing outcomes

Alice inspects a failed job, then asks a different command to wait for its success. Both views can display the same failed job state. Their command outcomes differ because the requests differ. Shared presentation makes the facts consistent while [CLI result contracts](cli-result-contracts.md#separate-command-success-from-background-work-success) determine what succeeded.

> **Status:** accepted presentation responsibilities and typed result boundary on 2026-10-28, recorded in [ADR-0097](../../../../docs/adr/ADR-0097-organize-rust-cli-by-command-family-and-typed-results.md). The linked output/result/change-review references own product semantics. Accepted organization does not establish implemented components, wire fields or a generic tracking schema. Exact schemas, error vocabulary and command mappings remain #156's work. Loading this reference authorizes no application changes.

## One owner for each decision

Command handlers request the operation through the generated SDK and produce typed client-owned results. The owning backend workflow determines permitted state, completed effects, counts and eligible recovery. Command-specific presenters select the concise human view. Shared output infrastructure owns rendering mechanics and machine framing under the approved contract.

For example, a human view can summarize a completed upload with its actual counts and warnings, while JSON exposes the same approved facts in fields. Presentation cannot infer that preparation, publication or evaluation also completed. Do not fill a missing denominator with zero or fetch additional protected items merely to make a complete-looking summary.

Follow [Rust CLI structure](../../inframeld-rust-standards/references/cli-structure.md) for accepted target placement and the command lifecycle. This reference owns the presentation responsibilities. [Output and automation](cli-output-and-automation.md) owns channels and descriptive dry-run, [results](cli-result-contracts.md) owns outcome/recovery meaning, and [change review](cli-change-review.md) owns before/after semantics. Keep those as single sources rather than copying their contracts into every presenter or language guide.

The [selected Rust CLI libraries](../../inframeld-rust-standards/references/cli-libraries.md) are accepted through ADR-0096. Rust Standards owns that dependency selection. Libraries supply rendering and input mechanics under this reference's responsibilities. ADR-0097 separately accepts file organization, and runtime integration remains delivery work.

<a id="proposed-shared-components"></a>

## Shared components

| Component family | What it centralizes | What remains with the command or owner |
| --- | --- | --- |
| Field lists | Labels, alignment, omitted/unknown presentation and safe identifiers. | Which permitted fields establish the requested result. |
| Tables | Headers, alignment, width, wrapping, empty views and plain-text presentation. | Typed rows, authoritative page bounds and meaningful columns. |
| Outcome summaries | Consistent outcome, reason and next-action presentation. | Whether admission, inspection or requested completion succeeded. |
| Change reviews | Shared Current/Proposed, Before/Now and Reviewed/Now rendering mechanics. | Reviewed inputs, confirmed effects and stale/conflict outcomes. |
| Diagnostics | Safe message presentation, stable approved codes, identifiers and hints. | Error classification, current access and which actions are actually available. |
| Progress | Confirmed activity, named units, known/unknown counts and terminal/plain rendering. | Authoritative observations, cancellation acknowledgment and continuation eligibility. |
| Value formatting | Consistent human durations, sizes, timestamps, identifiers and unavailable values. | The typed value, approved units and JSON representation. |

These families are a small design system, not a requirement to create a trait or class for every row. Share implementation once real uses expose the common responsibility. Keep an explicit command presenter when the useful summary differs. Avoid a universal document tree or string-valued map that erases the typed machine result.

Use semantic styling such as headings, identifiers, warnings and proposed/confirmed changes in shared infrastructure. Keep the information understandable without color. Content arriving from names, provider text or other external sources needs safe terminal handling. A renderer must not reveal a protected value merely because it can escape control characters.

## Compose components from typed facts

A command presenter selects useful permitted facts and calls shared components. A field list can display a build's identity and state, followed by an outcome summary explaining that inspection succeeded while the build failed. The component renders those facts without deriving command success from the displayed resource state.

Keep command-specific labels, columns and available next actions explicit. Shared components own alignment, empty/unknown rendering, width, wrapping and semantic styles. Human row records may contain formatted values, while JSON serializes the approved typed command representation directly. A human table row is not a machine response model.

Pass resolved presentation policy and output capabilities into shared rendering rather than having each component rediscover global settings. Components can share low-level rendering helpers without requiring a universal document tree or one trait per primitive. A useful command-specific presenter remains explicit when its summary differs.

Longer commands report confirmed activity through a separate progress sink. That sink can render indicatif indicators on a terminal or useful bounded plain observations elsewhere. It cannot request another page, infer a denominator, poll a job independently or decide whether interrupted work may resume. Cancellation input and its acknowledgment retain their owning command/job contract.

## Machine and CI behavior

Treat output format, noninteractive execution, terminal capabilities and verbosity as independent policy inputs. CI friendliness is not a third implementation of the operation. A script can request JSON explicitly, and a noninteractive text invocation still needs predictable exits, no surprise prompts and readable diagnostics.

The existing [machine-channel contract](cli-output-and-automation.md#use-one-predictable-machine-channel) requires one final versioned object on stdout in ordinary JSON mode, including controlled failures. Explicit JSONL has separate framing. Human diagnostics/progress belong on stderr. Terminal detection cannot silently convert watch output to JSONL or change the JSON schema.

The shared output boundary handles controlled failures from parsing and execution, while preserving local-error versus backend-problem meaning. A lost response can remain uncertain. A killed process or broken stdout can leave incomplete output, so absence of a result is not proof of no effects. Follow the approved result and signal mappings rather than deriving exits from resource status or HTTP success alone.

Define raw export, completion scripts, help/version and secret-delivery interactions explicitly before adding stdout conflicts. Secrets and downloadable artifacts retain their dedicated channels. Do not bury them in the ordinary result envelope or serialize raw exception/debug structures to obtain JSON cheaply.

Disable interactive prompts when input is noninteractive or the caller explicitly selects no-input behavior. Missing required values fail with an actionable explanation. Generic confirmation never supplies missing values or authority. Color and animations must respect the actual destination's terminal capabilities. Paging must not block an automated invocation. Quiet mode cannot conceal a failed command or corrupt its promised machine result.

[Descriptive dry-run](cli-output-and-automation.md#explain-an-invocation-without-performing-its-operation) uses normal parsing/context and only the permitted bounded metadata checks. It does not perform the requested operation, including a read. It is not a second policy/planning engine, authorization reservation or approval. Do not promise zero network activity or literally zero infrastructure writes where same-identity metadata refresh and request logs are permitted.

## Behavior to qualify

For each concrete command, check approved JSON success and controlled failure, stream separation, absent/noninteractive inputs, and truthful command versus job outcomes. Test narrow terminal widths, color-free output and hostile control characters where the renderer supports those cases. Compare human/JSON counts, warnings, unknowns and recovery limits using the same authorized facts.

Use behavioral witnesses to establish that presentation adds no paid call, requested read or mutation. A test double may establish interaction ordering, but real SDK/provider/persistence claims still need their appropriate test boundaries. Do not create architecture/import/naming enforcement tests or a permanent command-registration framework to prove directory shape.

[clig.dev](https://clig.dev/#output) informs stream discipline, JSON, terminal-aware rendering and [noninteractive inputs](https://clig.dev/#interactivity). Inframeld's envelope, universal descriptive dry-run, precise outcome semantics and current-authority limits remain product contracts. Following the guidelines is not certification or proof of completed implementation.
