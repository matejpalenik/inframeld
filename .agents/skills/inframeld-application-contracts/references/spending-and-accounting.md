# Reserve and account for model spending

<a id="reserve-and-account-for-model-spending"></a>

Alice sets a monthly project limit while SupportBot runs several questions. Concurrent calls must reserve against the same remaining allowance. A lost provider response keeps an unresolved obligation rather than proving zero cost.

> **Status:** the internal job-backed accounting and Project policy foundation is implemented and qualified at its PostgreSQL boundary using controlled accounting evidence. Provider pricing and usage normalization, actual ModelGateway dispatch, synchronous model-call integration and public policy/client journeys remain unfinished. The broader workflows below retain their accepted behavior. Code and migrations own implemented internal shapes, while native OpenAPI owns delivered HTTP shapes.

## Approved accounting coordination

Alice and Bob each try to reserve USD 0.70 from the last USD 1. One short transactional boundary reserves against all applicable Project and operation limits, including unsettled holds. Only one request fits. Policy mutation and settlement share the same documented coordination order. Each call has one idempotent settlement and a captured policy/rate basis.

Use exact decimal accounting with an initial USD 0.000000000001 quantum. Round conservative reservations and normalized accounting debits upward at that quantum, retaining trustworthy usage and captured-rate evidence. Display rounding never drives allowance. Fail visibly rather than truncate or overflow. An estimate or caller-supplied zero rate does not establish a valid cap bound.

Final dispatch authorization rechecks current policy and qualified pricing/bounds. A reserved but not-yet-authorized call that no longer fits cannot send and may release its proven unused hold. Once dispatch authorization commits, a later policy edit cannot recall that call. Timeout, restart, cancellation, missing usage and a new month do not release unknown holds. Correction requires authorized, audited, call-bound evidence, not an arbitrary mark-free action.

Capture each call's UTC month at reservation. Its late settlement stays in that month, while calls reserved in a later month use the later Project period and the operation's cumulative limit still spans both. Raising a limit or starting a month never automatically resumes work. The accepted [PD-CONTRACTS-02](decision-spending-coordination.md#approved-resolution) owns exact outcomes, permitted projections and evidence requirements. The [internal foundation](#implemented-internal-accounting) implements the accounting boundary. Provider integration remains separate qualification, and accounting is not an invoice-accuracy guarantee.

<a id="implemented-internal-accounting"></a>

## Implemented internal accounting

Suppose an admitted job reserves a model call against Support's monthly limit. The [accounting service](../../../../apps/backend/src/inframeld_backend/shared/application/services/spending_accounting_service.py) retains the original operation, caller authority, job, call identity, meaning, captured UTC month and price basis. Reservation, accounting approval and automatic observation application require the existing `JobAttemptContextDTO`. They check current admitted authority and actual job ownership. Omitting an attempt does not select synchronous execution. Synchronous model-call accounting remains future integration within the accepted scope.

`approve_accounting` records only the financial precondition. It rechecks current policy and complete applicable totals, including unresolved obligations. A recovered approval is a receipt, not permission to send or repeat a provider request. Provider credentials, trustworthy pricing coverage, cancellation/fencing at actual dispatch and the ModelGateway connection remain separate responsibilities.

Policy writes and call transitions coordinate through the same Project accounting row. Each path checks its own current authority before accounting coordination. Job-backed calls also check actual job ownership, with the narrow pending-evidence case described below. Persistence adapters participate in the service's transaction and do not commit independently. Original operation limits remain cumulative across attempts and months. Exact rate and usage precision is retained until the final reservation or debit is rounded upward to the twelve-decimal USD quantum. A stored source reference or typed observation does not prove provider authenticity or complete billable-category coverage.

[Direct reader/writer reservation races](../../../../apps/backend/tests/integration/spending/test_spending_accounting_postgres.py) demonstrate the SQL coordination mechanism. Service races pair one current human job with another human's policy edit, or older stale-job evidence with newer current work. These controlled cases do not qualify two simultaneously admitted product workloads or provider dispatch.

Known amounts and obligations that cannot yet be quantified remain separate. For example, an uncapped call with unknown pricing can leave an unquantified obligation. Alice may subsequently install a finite monthly limit, but that edit preserves the obligation. New reservations and accounting approvals subject to that cap fail until applicable facts are complete and conservatively bounded. An earlier Project month's obligation stays in its captured month, while an applicable original operation limit still spans months. The [read projection](../../../../apps/backend/src/inframeld_backend/shared/infrastructure/readers/postgres_spending_ledger_reader.py) returns policy, revision, captured-month totals and unquantified counts from one statement. Inspection creates no accounting row. Remaining allowance is absent when the period is uncapped or its facts are incomplete, rather than treating unknown cost as zero.

### Retain evidence without changing financial facts

After current authorization and exact original-call binding checks, a recognized lost job fence can retain an observation as pending. This saves the evidence and advances the call revision without changing its financial state, charge, hold or approval. The normal pending return lets the owning transaction commit. Invalid binding, authorization failure, database failure and cancellation retain their rejection or rollback behavior. A pending observation is not a settlement or evidence that the provider charged nothing. Unresolved pending items keep applicable accounting facts incomplete.

Human reconciliation requires current `manage-budget` on the exact Project, the reviewed call revision, the specific pending evidence ID and retained authoritative evidence for the same call. It accepts no arbitrary replacement amount or mark-free flag. The service saves the selected proof, audit and the [resolution's original outcome](../../../../apps/backend/src/inframeld_backend/shared/application/dtos/spending_evidence_resolution_dto.py) together. Identical completed resolution replay checks current authority before returning that outcome, without applying another debit. Changed proof binding conflicts.

Financial application and pending-item resolution are distinct. Applying proof to settle a call or resolve one pending item does not silently resolve the proof's own pending marker or another item. Original evidence and earlier financial receipts remain unchanged. Each pending item needs its explicit evidence-backed resolution. Recovering an older resolution or financial receipt returns its original result even after a later correction, not today's ledger state. The [recovery scenarios](../../../../apps/backend/tests/integration/spending/test_spending_recovery_postgres.py) cover these distinctions.

### Change policy without replacing the ledger

The [internal policy service](../../../../apps/backend/src/inframeld_backend/shared/application/services/project_spending_policy_service.py) separates `inspect-budget` from human-only `manage-budget`. A policy write checks current exact authority before reservation or replay, uses its own reviewed policy revision and commits policy, audit and original result together. Completed replay returns the original result before fresh-write revision checks. Policy edits do not rewrite calls, release obligations, change an operation limit or resume work. There is no automatic monetary default. Accounting obligations and evidence outlive expiring operation/replay metadata. Only the small policy replay receipt follows that metadata's retention.

This component supplies no public HTTP, SDK, CLI, browser or import budget workflow, and no application-key authentication. Controlled evidence tests establish internal behavior, not qualified provider facts or a usable human journey. The remaining ModelGateway/pricing/synchronous work in #123 and public budget-management work in #190 remain open.

Migration [0018_spending_accounting](../../../../apps/backend/migrations/versions/0018_spending_accounting.py) follows `0017_project_creation`. Its downgrade refuses retained policy, operation, call, evidence or policy-result records. Follow the existing [controlled maintenance procedure](../../../../docs/development/operations/upgrades.md#upgrades) and [ADR-0037](../../../../docs/adr/ADR-0037-use-controlled-migrations-and-coordinated-maintenance-upgrades.md). The retained-record check assumes that maintenance boundary and does not exclude live writers. Do not erase accounting history to force a downgrade.

<a id="expose-policy-administration-and-feedback-through-their-owners"></a>

### Expose policy administration and feedback through their owners

Enforcing a spending limit and changing that limit are different capabilities. Setup, CLI management and configuration import must all use the same guarded application operation for policy changes.

Authorized humans and applications may inspect permitted budget information. Only an active human with explicit project-budget permission may set, raise, lower or remove the project limit. Permission to use a model or import configuration is not enough. Confirmation flags cannot change who is eligible.

For example, SupportBot may import Pipeline settings while preserving the destination limit. If it asks to apply a different limit, reject that request rather than silently skip it. A permitted policy change preserves accounting history and operation limits. Check current authority and the reviewed revision, and save the required audit record. [Budget management](#budget-policy-authority) owns these rules. The [Access catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) selects Project `inspect-budget` and human-only `manage-budget`. Retains the accounting/policy wire schemas.

Trace inspection, trace-policy changes and deletion are also separate capabilities:

- Humans and applications may inspect pipeline traces with explicit inspection permission and current source access. Query permission alone is insufficient.
- Only an authorized human may change a project's tracing or retention settings.
- Explicit deletion of past traces needs a separate human deletion permission.

[Trace authority](../../inframeld-pipelines/references/query-tracing-and-privacy.md#trace-authority) owns these transitions. The Access and tracing contracts must represent the three outcomes separately, not invent one all-powerful tracing-admin permission.

An application import can preserve destination policy. If it explicitly requests a change it cannot perform, reject the known-invalid plan before changing resources. Neither import permission nor the worker's service identity supplies the initiating caller's missing permission. Normal expiry and source erasure remain backend cleanup and need no fresh human login per record. These requirements define no new MCP tools, routes, wire identifiers or generated schemas.

CLI feedback capability adds CLI feedback delivery, not new feedback semantics: use existing own-answer read/write contracts and the authorized reporting projection. Report counts, eligible-receipt coverage and comments with current filtering. Keep own-rating authority separate from project-wide inspection. Direct Pipeline querying is not a live receipt. No new MCP tool follows from these CLI capabilities.

Suspension/restoration contracts distinguish the immediate Access block, independent identity-provider cleanup and deliberate restoration. Privileged scoped operator recovery is a separate host-maintenance boundary, not a normal bearer-token API bypass. Concrete action mappings and additional request/result schemas belong to the named specification prerequisites in the [V1 scope](../../inframeld-architecture/references/v1-scope-and-extension-boundaries.md). This guide does not invent wire identifiers or claim generated contracts have changed.

Return preparation and publication outcomes separately. A ready-but-unpublished version is not a failed build or successful deployment. An absent/ambiguous/unauthorized target and a changed reviewed revision cannot trigger fallback to another target, fan-out, or a blind retry with newer state. Repeated requests find their original captured inputs and target before resolving current configuration again. No endpoint paths, new HTTP error codes, physical tables or wire types are mandated by these logical capabilities. Specify and test those contracts before implementation.

<a id="spending"></a>

<a id="cost-estimates-and-spending-admission"></a>

## Cost Estimates and Spending Admission

Alice gives a project a USD 20 calendar-month allowance and an evaluation a USD 1 limit. Customer queries running at the same time consume the same project budget. Both limits are optional. Never select an amount silently.

The project period begins at midnight UTC on the first of each month. The operation limit instead follows that operation across retries, continuation and month boundaries. Changing CLI context or rotating credentials resets neither accounting record.

Inframeld owns spending accounting. The accepted provider integration uses qualified LiteLLM pricing, token-counting and usage utilities without deploying a separate model gateway. That pricing and normalization integration remains unfinished and is not qualified by the internal ledger tests.

Show a best-effort estimate before upload, refine it after processing and summarize observed usage afterward. Include where the prices came from, how recent they are and the assumptions used. Private-model pricing may be unavailable. Local Ollama has no external model API charge, but still consumes compute. An estimate is neither a provider invoice nor a conservative upper bound used to reserve spending.

Before each chargeable model call:

1. Prepare the actual payload within its limits. For generation, enforce a maximum output allowance and include every applicable billable category. Average answer length is not an upper bound.
2. In one PostgreSQL transaction, reserve enough allowance against every applicable limit. Count both confirmed costs and existing reservations, called **holds**, so concurrent calls cannot each spend the same remaining allowance.
3. Close the transaction before contacting the provider.

Every model role, optional probe and repair call follows this process. Available budget never substitutes for permission to make the call.

After a call, record its cost once using trustworthy usage and the captured rates. This is **settlement**. Release only the unused part of its hold. Use fixed-precision decimal amounts and qualified conservative rounding.

Release a hold when the call is known not to have been sent. Keep it unresolved when dispatch may have happened but the outcome is unknown, including timeouts, cancellation, missing usage or a lost acknowledgment. Restarting a worker or letting its lease expire does not prove the provider charged nothing.

Record any overage honestly and stop further affected spending until it is resolved. A late settlement belongs to the UTC Project month captured when that call reserved its budget. A later call reserved in a new month uses the new month. The operation's cumulative limit still applies across both months.

With a monetary limit enabled, do not dispatch if prices are unavailable or a conservative bound cannot cover the billable work. An authorized policy or pricing change must make the call admissible first. If accounting itself is unavailable, capped work cannot start.

Without a cap, unknown pricing need not block otherwise supported and authorized use, but disclose that uncertainty. A familiar model alias or an arbitrary zero rate does not prove that execution is free and local.

When the budget is exhausted, stop new calls and keep completed work. Do not shrink the corpus or switch models to continue. Use ordinary job failure and recovery outcomes, not a new paused-job system. A new month does not automatically restart failed work.

Changing a shared limit requires its own current permission and audit record. The accepted [PD-CONTRACTS-02](decision-spending-coordination.md#approved-resolution) owns coordination, rounding, captured periods and evidence-backed reconciliation. Qualification must cover concurrency, rounding and providers. This design is not an invoice-level spending guarantee or evidence that those tests ran.

<a id="budget-policy-authority"></a>

<a id="manage-the-policy-separately-from-enforcing-it"></a>

### Manage the policy separately from enforcing it

Alice sets a USD 20 monthly project budget. SupportBot runs evaluations until a new model call cannot fit. The call is refused. The bot cannot raise the limit to keep itself running. An explicitly authorized human may review and change the limit to USD 50. That change saves policy only: eligible work must be resumed explicitly through the ordinary recovery operation.

V1 separates three actions:

| Action | Permission boundary |
| --- | --- |
| Inspect budget information | Humans and applications need `inspect-budget` on the exact Project and may read only the information they are currently permitted to see. |
| Execute model work | Authorized workloads may spend within all applicable limits. |
| Set, increase, decrease or remove a project limit | Only an active human with `manage-budget` on the exact Project may do this. Being human is not enough. Applications cannot receive this capability through model-use or import grants. |

The [reviewed Access catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) owns these accepted actions/targets. The model contract still owns accounting visibility, policy schemas and transactional coordination. The internal policy service is implemented. Public budget-management contracts and journeys remain work in #190, separate from the internal accounting foundation.

Apply that same rule in setup, ordinary management and configuration import. An application import may keep the destination budget while recreating otherwise authorized resources. If it explicitly requests a budget change, report the human-only restriction before executing the known-invalid plan. Do not silently drop that step, borrow a human login or claim the requested plan succeeded.

Current authority and expected state are rechecked when a permitted mutation commits. If authority is lost after earlier import work committed, preserve those completed outcomes and stop the affected unfinished work under ordinary recovery rules. This choice does not change cumulative operation-limit behavior or decide authority for other project policies.

Alice changes the project's monthly limit from USD 20 to USD 10 after USD 12 has already been settled and USD 1 remains reserved. The update changes the policy, not the ledger: it does not erase spending, release the hold or make the available allowance positive. Further calls that cannot fit are refused. Already-dispatched calls retain normal settlement and uncertainty handling.

One application-layer capability exposes authorized inspection and human-only setting, replacement and explicit removal of the project limit. Here, application-layer means backend business orchestration, not permission for an application account to mutate policy. CLI setup/management and TOML import must use this capability when delivered. Neither may write a separate copy of policy. Recheck current human eligibility/change authority and the reviewed policy revision, coordinate mutation with concurrent reservations, and commit policy/audit together. Apply the accepted [accounting contract](decision-spending-coordination.md#approved-resolution). Concrete native request schemas remain implementation work within that contract. A lost acknowledgment recovers the original mutation rather than applying it over a newer policy.

Increasing or removing a limit also preserves consumed amounts and unresolved obligations. It neither changes existing operation limits nor resumes stopped work. Setup retains the current policy by default. Import preserves destination policy unless its explicit apply choice is separately authorized. A model-use grant, generic import approval or `--yes` is not budget-administration authority. No monetary default is prefilled, and no provider test or model call follows saving a policy. V1 has only project and operation limits. Account, user, connection and organization budget hierarchies remain deferred.

Connection TOML exports only current supported non-secret access settings and authentication requirements. Credentials are separately provisioned and consumer model settings remain with profiles/pipelines/evaluators. [Configuration portability](configuration-export-and-import.md) preserves ordinary live-impact and embedding guards during import.

<a id="retained-logical-information"></a>

## Retained logical information

| Information | Owner and constraint |
| --- | --- |
| Spending policy, accounting period, call reservation and settlement | Gateway/application accounting in PostgreSQL. Optional UTC-calendar-month project limit and cumulative operation limit. A reviewed policy mutation records its revision and audit without replacing accounting history. Uniquely attributed call/period, captured price basis, fixed-precision amounts and unresolved holds survive policy changes, retries and restart. No account-level ceiling, credentials or full prompts are needed for accounting. |

The accepted accounting projection includes optional policy/revision, UTC period, settled total, unresolved holds, remaining allowance including negative values, pricing provenance and permitted partial/uncertain operation state. Keep call and reservation identity, captured rate/policy basis and correction evidence without raw prompts or secrets. These are logical facts, not public field names. The [spending migration](../../../../apps/backend/migrations/versions/0018_spending_accounting.py) owns physical storage, and the [internal projection](../../../../apps/backend/src/inframeld_backend/shared/application/dtos/spending_projection_dto.py) owns the delivered application shape.
