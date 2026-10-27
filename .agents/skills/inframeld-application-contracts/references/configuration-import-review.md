# Review destination-aware configuration changes

Bob reviews Alice’s definitions against an existing installation. Names resolve to destination identities. Reuse, creation and supported updates need explicit comparison and current authority before the import changes resources.

<a id="destination-review"></a>

## Destination Review

V1 creation of configurable resources is human-only. An application may review/import eligible changes to existing resources and explicitly reuse compatible definitions. A missing dependency or changed immutable profile requiring creation makes its plan ineligible: reject the known-invalid plan before mutations and report the resource an authorized human must provision. A subsequent import uses a new reviewed plan against those destination IDs. Neither a Create grant record nor a saved human login makes application creation eligible. [The provisioning contract](../../inframeld-access-models/references/actions-and-initial-grants.md#provisioning) owns this boundary. Ordinary operational output such as versions and cases remains supported.

For Bob, `legal-research` names a candidate project in his selected installation, not Alice's UUID. He selects an existing destination or separately creates one. The importer validates local files offline first. Destination-aware dry-run is a distinct read-only review.

- Resolve dependencies by project/type name, then retain permanent IDs. A matching name proves neither semantic equivalence nor authority.
- For a human import, propose creation for missing resources. Application imports require those resources to exist. Propose explicit reuse for matching configuration. Different configuration is a conflict until deliberately resolved through a supported guarded update or corrected input.
- Changed immutable processing/embedding meaning requires a distinct named profile. Do not mutate an existing profile to satisfy an import.
- Review each source audience requirement against permitted destination groups, even when names match. Group creation is separate. Save destination IDs. Import neither copies memberships/grants nor changes existing document audiences.
- Preserve destination project budget/tracing policies unless a separately authorized reviewed update explicitly changes them. Imported settings cannot override operator restrictions.
- Shared connection updates retain live-impact review, current revision/dependency checks, credential binding and the embedding-compatibility veto. Import is not a privileged shortcut.

**Example: importing with an application key.** Git contains a USD 100 project limit. SupportBot's destination has a USD 20 limit. With current access to the necessary definitions and otherwise authorized resource operations, the default preserve choice keeps USD 20 and reports the intentional difference. It does not invoke budget mutation. If SupportBot explicitly requests applying USD 100, the plan is ineligible: only an explicitly authorized human may set, raise, lower or remove the project limit in v1.

Reject that known-invalid plan before its resource mutations. Do not silently omit the requested change or switch to a saved human account. The user may separately choose a new plan that preserves the budget, or have an authorized human perform a separately reviewed change.

This rule also covers first setting a limit, lowering it and applying explicit no-limit. A file, import grant or confirmation cannot make an application eligible. Permission to inspect protected policy information remains separate. [Budget management](spending-and-accounting.md#budget-policy-authority) owns mutation and accounting. Authority can still be revoked after review: ordinary owners recheck at commit, preserve completed import steps and report partial outcomes without replaying a policy over newer state.

**The same preserve/apply distinction applies to tracing and retention.** Suppose Git requests tracing on for 30 days but the destination uses off for 7 days. These are illustrative settings, not new defaults. SupportBot may import otherwise authorized resources while preserving off/7 days. Report the intentional difference only within its disclosure authority. It cannot apply on/30 days, disable capture or change retention even if it can inspect pipeline traces.

Reject that known-ineligible explicit plan before mutations. Only an active human with current project trace-policy authority may approve apply through, under operator constraints and reviewed state. Do not change identity or silently substitute preserve.

Reducing retention must disclose possible expiry of existing history. It uses the ordinary retention operation, not an import-owned cleanup mechanism. Import never transfers or explicitly deletes trace history. The separate human-only delete-history action requires separate deletion authority. It is not implied by policy apply or inspection. Automatic expiry and source erasure continue through ordinary backend workflows. [Observability](../../inframeld-pipelines/references/query-tracing-and-privacy.md#trace-authority) specifies this boundary. Must expose it and must qualify preservation, denial and partial recovery.

<a id="credentials-stay-separate"></a>

## Credentials Stay Separate

TOML contains authentication requirements, never credential values, encrypted secrets or references that automatically discover arbitrary secrets. After configuration import, Bob sees which connections/sources require credentials and can reuse the same protected screens as ordinary model/source setup. Existing credentials remain unchanged unless explicitly replaced.

Human input uses hidden entry. Automation uses protected files or stdin, not argv or environment secrets. Human-only provider-credential/grant administration remains human-only even when a surrounding import is scriptable. Sources use explicit backend-configured identity or source-specific credentials. Never laptop ambient credentials, a human login token or another resource's key. Saving configuration or credentials performs no synthetic test or sync implicitly.

For a model connection, an exported API-key authentication requirement is not the key itself. Bob separately supplies the raw provider key. The backend adapter later constructs the known provider header. Inframeld login/application credentials cannot fill that slot. A supported metadata read uses the same destination-bound credential checks, not the exporting installation's key or a direct CLI request. Missing keys leave configuration saved but not usable for required authenticated calls. Import never claims successful authentication. Origin/auth-method changes cannot preserve a key implicitly. [Provider authentication](../../inframeld-access-models/references/provider-credential-storage.md#provider-authentication) owns these rules.

<a id="first-bind-the-reviewed-input"></a>

### First bind the reviewed input

Validate the complete selected input and resolve every known conflict before resource mutations. Bind the actual target/account/project, supported definition content, destination identities, create/reuse/update choices, policy choices, required acknowledgments and relevant expected revisions. A path on Bob's laptop is not a durable copy of those definitions. Missing credentials are separate unmet requirements, not permission to send a probe or borrow another identity's key.

Before beginning resource mutations, recheck the reviewed input, current authority and relevant destination state. A known change invalidating that review stops the import without resource mutations. This is not a promise that concurrent changes cannot happen a moment later: every owning operation still checks its relevant authority, revisions and dependencies at its ordinary boundary. No global project lock or all-or-nothing transaction is selected here. Unrelated destination activity does not by itself justify inventing a whole-project revision conflict. The import contract still needs the precise reviewed checks for each action.

<a id="case-2-the-review-is-stale-before-resource-changes"></a>

### Case 2: the review is stale before resource changes

Bob reviewed Pipeline revision 17. Alice saves revision 18 before the import's pre-mutation checks. Report that the review changed and that **no resource changes were made by this import**, if confirmed. Show permitted reviewed/current values using the [shared delta presentation](cli-change-review.md#cli-change-presentation), not a proposed update disguised as a completed one. Ask Bob to review the current destination and the intended incoming settings again. Do not accept revision 18 automatically, reinterpret a create as reuse or turn generic confirmation into overwrite authority.

Internal admission/recovery records may already exist. "no resource changes" does not mean that no request/job metadata was written. If an acknowledgment is lost, recover its outcome before making even this narrower claim. Exact admission/precondition ordering remains work.
