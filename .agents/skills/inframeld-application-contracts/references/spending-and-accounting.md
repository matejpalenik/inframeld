# Reserve and account for model spending

<a id="reserve-and-account-for-model-spending"></a>

Alice sets a monthly project limit while SupportBot runs several questions. Concurrent calls must reserve against the same remaining allowance. A lost provider response keeps an unresolved obligation rather than proving zero cost.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

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

Inframeld owns spending accounting. It uses qualified LiteLLM pricing, token-counting and usage utilities without deploying a separate model gateway.

Show a best-effort estimate before upload, refine it after processing and summarize observed usage afterward. Include where the prices came from, how recent they are and the assumptions used. Private-model pricing may be unavailable. Local Ollama has no external model API charge, but still consumes compute. An estimate is neither a provider invoice nor a conservative upper bound used to reserve spending.

Before each chargeable model call:

1. Prepare the actual payload within its limits. For generation, enforce a maximum output allowance and include every applicable billable category. Average answer length is not an upper bound.
2. In one PostgreSQL transaction, reserve enough allowance against every applicable limit. Count both confirmed costs and existing reservations, called **holds**, so concurrent calls cannot each spend the same remaining allowance.
3. Close the transaction before contacting the provider.

Every model role, optional probe and repair call follows this process. Available budget never substitutes for permission to make the call.

After a call, record its cost once using trustworthy usage and the captured rates. This is **settlement**. Release only the unused part of its hold. Use fixed-precision decimal amounts and qualified conservative rounding.

Release a hold when the call is known not to have been sent. Keep it unresolved when dispatch may have happened but the outcome is unknown, including timeouts, cancellation, missing usage or a lost acknowledgment. Restarting a worker or letting its lease expire does not prove the provider charged nothing.

Record any overage honestly and stop further affected spending until it is resolved. A late settlement belongs to the project's original admission period. The operation's cumulative limit still applies.

With a monetary limit enabled, do not dispatch if prices are unavailable or a conservative bound cannot cover the billable work. An authorized policy or pricing change must make the call admissible first. If accounting itself is unavailable, capped work cannot start.

Without a cap, unknown pricing need not block otherwise supported and authorized use, but disclose that uncertainty. A familiar model alias or an arbitrary zero rate does not prove that execution is free and local.

When the budget is exhausted, stop new calls and keep completed work. Do not shrink the corpus or switch models to continue. Use ordinary job failure and recovery outcomes, not a new paused-job system. A new month does not automatically restart failed work.

Changing a shared limit requires its own current permission and audit record. [PD-CONTRACTS-02](decision-spending-coordination.md) owns the unresolved coordination choices. Qualification must cover concurrency, rounding and providers. This design is not an invoice-level spending guarantee or evidence that those tests ran.

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

The [reviewed Access catalogue](../../inframeld-access-models/references/actions-and-initial-grants.md#reviewed-capability-catalogue) owns these accepted actions/targets. The model contract still owns accounting visibility, policy schemas and transactional coordination. Budget management is the implementation ticket, not evidence that this design is implemented.

Apply that same rule in setup, ordinary management and configuration import. An application import may keep the destination budget while recreating otherwise authorized resources. If it explicitly requests a budget change, report the human-only restriction before executing the known-invalid plan. Do not silently drop that step, borrow a human login or claim the requested plan succeeded.

Current authority and expected state are rechecked when a permitted mutation commits. If authority is lost after earlier import work committed, preserve those completed outcomes and stop the affected unfinished work under ordinary recovery rules. This choice does not change cumulative operation-limit behavior or decide authority for other project policies.

Alice changes the project's monthly limit from USD 20 to USD 10 after USD 12 has already been settled and USD 1 remains reserved. The update changes the policy, not the ledger: it does not erase spending, release the hold or make the available allowance positive. Further calls that cannot fit are refused. Already-dispatched calls retain normal settlement and uncertainty handling.

One application-layer capability exposes authorized inspection and human-only setting, replacement and explicit removal of the project limit. Here, application-layer means backend business orchestration, not permission for an application account to mutate policy. CLI setup/management and TOML import use this capability. None writes a separate copy of policy. Recheck current human eligibility/change authority and the reviewed policy revision, coordinate mutation with concurrent reservations, and commit policy/audit together. The exact coordination protocol and request schemas must be reviewed before implementation. A lost acknowledgment recovers the original mutation rather than applying it over a newer policy.

Increasing or removing a limit also preserves consumed amounts and unresolved obligations. It neither changes existing operation limits nor resumes stopped work. Setup retains the current policy by default. Import preserves destination policy unless its explicit apply choice is separately authorized. A model-use grant, generic import approval or `--yes` is not budget-administration authority. No monetary default is prefilled, and no provider test or model call follows saving a policy. V1 has only project and operation limits. Account, user, connection and organization budget hierarchies remain deferred.

Connection TOML exports only current supported non-secret access settings and authentication requirements. Credentials are separately provisioned and consumer model settings remain with profiles/pipelines/evaluators. [Configuration portability](configuration-export-and-import.md) preserves ordinary live-impact and embedding guards during import.

<a id="retained-logical-information"></a>

## Retained logical information

| Information | Owner and constraint |
| --- | --- |
| Spending policy, accounting period, call reservation and settlement | Gateway/application accounting in PostgreSQL. Optional UTC-calendar-month project limit and cumulative operation limit. A reviewed policy mutation records its revision and audit without replacing accounting history. Uniquely attributed call/period, captured price basis, fixed-precision amounts and unresolved holds survive policy changes, retries and restart. No account-level ceiling, credentials or full prompts are needed for accounting. |
