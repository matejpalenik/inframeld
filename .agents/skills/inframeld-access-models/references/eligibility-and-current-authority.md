# Current account and credential eligibility

Alice authenticated before password recovery began. A later grant attempt must read current account and recovery facts before reserving or replaying work. An authenticated context is evidence for the attempt, not a permission certificate.

## Incoming credentials and admitted jobs

Fresh incoming requests and replays follow the [accepted key-boundary contract](decision-key-currentness.md#approved-resolution). Already admitted product jobs instead follow [current-principal authority](decision-admitted-work-authority.md#approved-resolution), using server-owned original scope/input and current worker ownership. Original credential expiry/replacement/revocation alone does not cancel them. Current account restrictions, required permissions and applicable human recovery generation still prevent later protected steps. This separate logical authority contract is not a new incoming credential family or an implemented bypass.

<a id="shared-principal-eligibility"></a>

<a id="one-shared-account-eligibility-decision"></a>

### One shared account-eligibility decision

Alice authenticated before recovery started. She now tries to grant Bob an action on Support. Her earlier session check cannot prove that she is still eligible. Access must read her current state for this attempt, deny the grant while recovery remains blocked, and avoid saving a grant, audit event or idempotency reservation. Repeating an earlier successful request still requires the same current authorization.

[ADR-0064](../../../../docs/adr/ADR-0064-centralize-principal-eligibility-and-keep-access-aggregates-focused.md) selects one common domain policy for product eligibility. It checks the observed account status and current recovery restrictions. Human authentication adds the human-kind requirement. Action authorization adds project membership and the exact grant. Delegation additionally requires an eligible human grantor and permission to grant the exact action. These policies reuse the common rule instead of each expressing recovery eligibility independently.

The shared input describes one current attempt. It carries the observed Principal and recovery facts together through the operation's records. It is not a saved permission, a new Principal status, or an extension of `AccessContextDTO`. Credential verification, provider identity eligibility and application-key lifecycle checks retain their separate owners. A valid token or key does not supply product authority.

Access authorization operations own the check sequence:

1. Load current facts for the exact caller and target. A grant change first acquires the required organization/project locks and holds them until the caller commits or rolls back.
2. Interpret authentication evidence against the stored principal kind and current OAuth observations. A kind mismatch is an internal contract failure. Non-current OAuth credentials receive the generic invalid-token response before visibility checks.
3. Apply project visibility before disclosing authority or recipient existence. A hidden project remains 404. For a visible project, a recovery block or missing action/delegation authority returns 403.
4. Require the operation-specific rules, including human-only restrictions where applicable. Grant authorization checks the actor before revealing an absent recipient.
5. Only then find or create the idempotent operation. A saved result does not bypass current authorization. Expected-revision handling still distinguishes replay from new work.

Read adapters should collect the eligibility and relationship facts for that attempt in one coherent typed projection where practical. An `EXISTS` expression may report a pending recovery obligation alongside membership and grant existence. It does not decide permission. Missing installation metadata or unavailable dependencies must fail closed, rather than look like no block. A facts reader must not hide an additional query by instantiating another executing reader just to supply one field.

One transaction may contain multiple statements. The [write coordination contract](grant-administration.md#how-the-database-gives-each-change-its-turn) still governs locks, current-state checks and writes. Recovery admission for a linked human must take the conflicting exclusive organization lock. [ADR-0082](../../../../docs/adr/ADR-0082-coordinate-first-admission-and-recovery-by-identity.md) additionally requires an [identity turn](identity-admission-coordination.md) before organization/project locks for first admission, recovery admission/completion and credential-state initialization. Recovery admission/completion and initialization now use this shared coordinator. First-admission integration remains future work. Never hold an Access transaction while waiting for Kratos, Hydra or a model provider.

The current [recovery admission writer](../../../../apps/backend/src/inframeld_backend/access/infrastructure/writers/postgres_identity_recovery_admission_writer.py) finds the organization through the verified authority/subject link and takes its exclusive lock before recording recovery. An identity without a local link can still receive a recovery record. The [grant facts reader](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/postgres_project_grant_change_facts_reader.py) takes a shared organization lock, then an exclusive project lock, before reading current authorization facts. If recovery commits first, the waiting grant reads its block and is denied. If the grant gets its locks first, recovery waits until that transaction finishes.

Each of these two adapters applies one fixed five-second deadline to its database work, including lock waits. The deadline is per adapter call, not per statement. Expiry raises `DependencyUnavailableError`, and the caller rolls back the transaction, including any partial admission or reservation. For the grant workflow, the application service owns this rollback through `TransactionManager`. The adapters never commit. These internal deadlines are separate from the configurable human-authentication provider/total budgets and do not cover later provider cleanup or the caller's final commit.

Recovery screens and authenticated cleanup callbacks remain usable under their own contracts while product access is blocked. The implemented `IdentityRecovery` aggregate protects cleanup-state transitions for the original flow. Its specific repository preserves the original admission metadata. Neither can recreate removed permissions, clear suspension or independently establish that no other recovery block remains. [Checklist persistence](recovery-completion.md#recovery-checklist-persistence) describes the current implementation boundary.

**Implementation status:** the shared eligibility input/policy is used by human authentication, Project action authorization and exact Project grant management. The [PostgreSQL recovery authorization tests](../../../../apps/backend/tests/integration/access/test_recovery_authorization_postgres.py) cover existing contexts, current authorization on replay, both recovery/grant ordering cases, timeout rollback, explicit block release and recovery recorded before a later local link. The recovery aggregate, repository and [local completion workflow](recovery-completion.md#recovery-completion-workflow) exist. Private native callbacks, bounded provider cleanup, proof reconciliation and [protected host continuation](host-maintenance.md#recovery-cleanup-continuation) are implemented. Complete first-local-admission integration and its concurrent qualification remain unfinished. [Bulk Hydra calls](recovery-provider-cleanup.md#hydra-cleanup-evidence) are qualified separately. [Application structure](architecture.md#shared-access-eligibility) owns component responsibilities, and [the data model](credential-and-recovery-records.md#principal-eligibility-inputs) distinguishes temporary inputs from stored records.

The complete grant service also verifies that current management facts bind the actor and Project requested by its Command. It checks those IDs before reserving work or returning a replay. If they differ, it raises an internal runtime error and rolls back. The existing HTTP error handler returns a generic 500. After a match, reservation, grant persistence and audit use scope from authorization, while the unchanged Command supplies the requested grant details. This scope check does not replace current principal, Project visibility or exact-delegation policies.

<a id="accepted-browser-currentness"></a>

### Recheck bound browser evidence after restoration

**Implemented credential fence under [ADR-0127](../../../../docs/adr/ADR-0127-fence-human-authentication-evidence-at-restoration.md).** The shared evaluator requires the browser binding captured before [final same-cookie verification](browser-sessions.md#restoration-evidence-cutover) to match current actor, installation, provider identity and credential version before protected disclosure, reservation/history lookup, replay or mutation. It applies the same neutral current-facts type to browser and human OAuth evidence.

Facts readers report those current observations under the existing scoped transaction/lock rules. The evaluator interprets evidence, while the owning policy decides currentness. A version never supplies membership or permissions and does not replace current status, independent recovery restrictions or exact operation authority. Missing required browser binding or current facts cannot be accepted as an older compatible path. No public credential/version details or new error vocabulary is selected here.

The still-unfinished restoration transaction must advance the version once with its state/revision/audit/original outcome. A replay restores neither grants nor a former credential generation. Alice's stale evidence fails after cutover while Bob is unchanged. Fresh post-cutover verification retains the explicitly accepted possibility of a late-created currently valid Kratos session. It proves neither password-save provenance nor the legitimate-identity/security review required for restoration.

<a id="project-membership-grant-model"></a>

The supported use-only grant applies these checks before its [load, business action and save sequence](../../inframeld-python-standards/references/services-and-use-cases.md). Its repository supports attributed additions, not membership provisioning or arbitrary grant updates. The [aggregate/repository example](../../inframeld-python-standards/references/aggregates-and-repositories.md) owns snapshots, persistence failures and transaction lifetime.

<a id="human-credential-version-flow"></a>

<a id="carry-credential-evidence-without-freezing-authorization"></a>

### Carry credential evidence without freezing authorization

[Credential versioning](human-cli-credential-lifecycle.md#human-credential-versions) extends the consent and human bearer chains. Access owns the version value and validity policy. Typed application records carry binding evidence and current observations. PostgreSQL adapters own scoped persistence and coherent projections. Hydra adapters alone map private provider metadata.

For consent allowance, the service first reads and validates Hydra's trusted request. Unsupported access stops before initialization or browser verification. For supported access, it initializes/captures the version and block, verifies the browser, then reads current state before approval. This initializer is a narrow provider-workflow metadata capability with its own bounded short transaction. It closes that transaction before provider verification. It does not provision an account, execute a product Command or advance an existing version. GET inspection and denial remain read-only with respect to version state.

Bearer verification returns a `HumanOAuthCredentialBindingDTO`. Authentication checks current state, then returns the actor with that non-secret evidence in `AccessContextDTO`. [Explicit evidence variants](credential-and-recovery-records.md#access-context-evidence) distinguish browser, OAuth and application-key callers. Authorization facts readers compose exact identity-link and version lookup into their existing statement, using pure query construction rather than executing another reader. Both authorization families reject stale credentials before retry lookup or mutation. The shared product-eligibility policy also denies a non-current credential.

Existing organization/project locks and application-owned grant transactions stay in place. Recovery admission advances its identity version inside its caller's transaction. The accepted identity prerequisite will also coordinate the initializer without extending its transaction across browser verification. No database session waits for an external provider. A captured version identifies the credential's origin and never certifies future eligibility or permission.

<a id="credential-query-and-policy-boundaries"></a>

<a id="separate-stored-credential-observations-from-decisions"></a>

### Separate stored credential observations from decisions

Alice presents CLI version 6, while her current stored version is 7. SQL establishes whether her presented installation and provider identity match the local actor's identity link. It returns that relationship and the stored version together. The domain policy then requires both a matching binding and an equal version. It does not compare the credential's identity fields with copies of those same fields.

| Component | Responsibility |
| --- | --- |
| `HumanCredentialStateQueries` | Construct typed SQL expressions. OAuth expressions accept the exact binding, not an entire Access context. They open no sessions and execute nothing. |
| PostgreSQL facts readers | Execute the scoped coherent projection and return the stored principal, recovery flag and neutral `HumanCredentialFactsDTO`. Browser and human OAuth callers require an observation record, including failed matches or absent versions. Application evidence uses separate key facts. |
| `PostgresHumanCredentialStateMapper` | Preserve narrow raw-four conversion through `to_state()` and separately map complete authentication/link state through `to_authentication_state()`. Missing installation metadata remains unavailable state. The mapper initializes nothing and decides no permission. |
| `PrincipalAccessEvaluationService.evaluate()` | Interpret the three evidence variants, reject stored-kind mismatches and construct `PrincipalAccessPolicyInput` using the credential policy. It performs no I/O and needs no extra injected capability. |
| `HumanCredentialPolicy` | Decide currentness from the checked actor binding and presented/stored versions. Bearer authentication retains its separate full-binding comparison against authoritative state. |

Both human evidence families require current credential observations. Missing observations are an internal contract failure, while an unsuccessful actor/installation/identity match or absent/different version produces non-current credentials. The existing `oauth_credential_facts` field and evaluator keyword now carry `HumanCredentialFactsDTO` for browser and OAuth callers. Stale human evidence is rejected before visibility, permission, reservation or replay. Application-key evidence retains its independent current-key facts and policy.

[ProjectActorQueries.header()](../../../../apps/backend/src/inframeld_backend/access/infrastructure/readers/project_actor_queries.py) keeps the shared seven-field Project-actor projection: stored Principal and Project, installation UUID, membership, pending recovery, exact linked-identity match and nullable stored version. Scoped readers append their operation-specific observations. [PostgresProjectActorMapper.action()](../../../../apps/backend/src/inframeld_backend/access/infrastructure/mappers/postgres_project_actor_mapper.py) preserves its `access`, `principal`, `project`, `member`, `recovering`, `linked`, `version` and `granted` keywords. This is database adapter compatibility, not a public response type or authority certificate.

The action reader still executes one statement. The grant reader retains its three coordination statements followed by one facts SELECT. Both use the caller's transaction, and ORM projections refresh already loaded state. [PostgreSQL observation tests](../../../../apps/backend/tests/integration/access/test_human_credential_facts_postgres.py) exercise these query counts and current principal status. No reader calls another executing reader to fill a field.

<a id="typed-authorization-capabilities"></a> <a id="temporary-authorization-requests"></a> <a id="typed-authorization"></a>

### Typed authorization capabilities

Original-request lookup has a separate read capability. It validates the expected family/action and exact scope, checks current eligibility and the selected family's current authority before any reservation-history read, then allows only an exact retained authority-binding match. The expected guard does not certify original meaning. The retained binding does not certify current permission. The [lookup contract](../../inframeld-application-contracts/references/operation-recovery-contracts.md#original-request-lookup) owns the public non-disclosure matrix and supported families. This read does not execute an action or recheck a grant recipient as a new assignment.

Alice performing a project action and assigning Bob permission to perform it are different decisions. Both need current eligibility, but assignment also checks delegation authority and the recipient. [ADR-0067](../../../../docs/adr/ADR-0067-standardize-authorization-capabilities-with-typed-requests.md) gives both a common calling convention without combining their rules.

[`Authorizer[RequestType, ResultType]`](../../../../apps/backend/src/inframeld_backend/access/application/protocols/authorizer.py) declares the abstract keyword-only method `require_authorization(access, request)`. The family Protocol specializes request and result types. Concrete services and test doubles explicitly inherit their family and mark the method with `@override`. Inheriting this required behavior does not create an empty marker interface.

| Family | Request | Result | Existing consumer |
| --- | --- | --- | --- |
| `ActionAuthorizer` | `ProjectActionAuthorizationRequestDTO`: project and action selected by the trusted workflow. | `ProjectActionAuthorizationDTO`: matched organization and project. | `ProjectOperationAdmissionService` |
| `ProjectGrantManagementFactsReader` | Authenticated access, Project, recipient and exact action. | `ProjectActionGrantManagementFactsDTO`: current actor, target, recipient, credential and remaining-grantor observations under coordination. | `ProjectGrantChangeService`, which applies the existing policies and constructs checked `ProjectGrantAuthorizationDTO` scope. |

Action-authorization requests are temporary frozen, slotted Access application DTOs, independent of business Commands and HTTP models. Grant management keeps requested IDs and current facts separate from its policy decisions. They add no persisted state. Field annotations establish neither existence nor permission. They carry no retry context, fingerprint or expected revision. The owning services preserve their existing facts readers, visibility ordering and domain policies. `ActionAuthorizationService` converts its request into the existing `ProjectActionTargetDTO` for the reader. Shared eligibility still has one domain-policy owner.

Both consumers compare the returned project with the requested project before reservation or replay. A mismatch raises `RuntimeError`. After matching, use scope from authorization downstream and preserve the requested business input unchanged. The grant service owns rollback through its transaction manager. The admission helper never commits or rolls back on its own, and its caller retains transaction ownership.

Reuse the ordinary action family for another operation needing the same kind of exact project-action check. The trusted application workflow chooses the required action, rather than taking a permission selector from HTTP input. Add another family when a decision needs materially different inputs or rules. The shared Protocol standardizes signatures and does not execute policy, force a caller to authorize or make a result a reusable permission certificate. Behavioral denial, scope-mismatch, replay and database tests establish the actual boundaries. This qualifies two existing consumers, not a second complete product write workflow.
