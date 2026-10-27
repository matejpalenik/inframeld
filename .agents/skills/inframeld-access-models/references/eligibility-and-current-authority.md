# Current account and credential eligibility

Alice authenticated before password recovery began. A later grant attempt must read current account and recovery facts before reserving or replaying work. An authenticated context is evidence for the attempt, not a permission certificate.

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

**Implementation status:** the shared eligibility input/policy is used by human authentication, project action authorization and the supported use-only human grant command. The [PostgreSQL recovery authorization tests](../../../../apps/backend/tests/integration/access/test_recovery_authorization_postgres.py) cover existing contexts, current authorization on replay, both recovery/grant ordering cases, timeout rollback, explicit block release and recovery recorded before a later local link. The recovery aggregate, repository and [local completion workflow](recovery-completion.md#recovery-completion-workflow) exist. Private native callbacks, bounded provider cleanup, proof reconciliation and [protected host continuation](host-maintenance.md#recovery-cleanup-continuation) are implemented. Complete first-local-admission integration and its concurrent qualification remain unfinished. [Bulk Hydra calls](recovery-provider-cleanup.md#hydra-cleanup-evidence) are qualified separately. [Application structure](architecture.md#shared-access-eligibility) owns component responsibilities, and [the data model](credential-and-recovery-records.md#principal-eligibility-inputs) distinguishes temporary inputs from stored records.

The complete grant service also checks that authorization returned the project requested by its Command. It compares the IDs immediately after authorization, before reserving work or returning a replay. If they differ, it raises an internal runtime error and rolls back. The existing HTTP error handler returns a generic 500. After a match, reservation, grant persistence and audit use scope from authorization, while the unchanged Command supplies the requested grant details. This scope check does not replace current permissions or the authorizer's project/organization checks.

<a id="project-membership-grant-model"></a>

The supported use-only grant applies these checks before its [load, business action and save sequence](../../inframeld-coding-standards/references/services-and-use-cases.md). Its repository supports attributed additions, not membership provisioning or arbitrary grant updates. The [aggregate/repository example](../../inframeld-coding-standards/references/aggregates-and-repositories.md) owns snapshots, persistence failures and transaction lifetime.

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
| PostgreSQL facts readers | Execute the existing coherent facts SELECT and return the stored principal, recovery flag and `HumanOAuthCredentialFactsDTO`. OAuth callers always receive an observation record, including failed matches or absent versions. Other evidence families receive no OAuth facts. |
| `PostgresHumanCredentialStateMapper` | Share database-to-state conversion between the independent state reader, initializer and recovery-admission writer. Missing installation metadata remains unavailable state. The mapper initializes nothing and decides no permission. |
| `PrincipalAccessEvaluationService.evaluate()` | Interpret the three evidence variants, reject stored-kind mismatches and construct `PrincipalAccessPolicyInput` using the credential policy. It performs no I/O and needs no extra injected capability. |
| `HumanCredentialPolicy` | Decide currentness from the checked actor binding and presented/stored versions. Bearer authentication retains its separate full-binding comparison against authoritative state. |

Both authorizers invoke the evaluator after a non-missing facts result. Missing OAuth observations are an internal contract failure, while an unsuccessful match or missing/different version produces non-current credentials. Authorizers translate that result into the existing generic invalid-credential failure before visibility, permission, reservation or replay. Browser/application paths explicitly supply true for this inapplicable OAuth check without verifying their sessions or keys again.

The action reader still executes one statement. The grant reader retains its three coordination statements followed by one facts SELECT. Both use the caller's transaction, and ORM projections refresh already loaded state. [PostgreSQL observation tests](../../../../apps/backend/tests/integration/access/test_human_credential_facts_postgres.py) exercise these query counts and current principal status. No reader calls another executing reader to fill a field.

<a id="typed-authorization-capabilities"></a> <a id="temporary-authorization-requests"></a> <a id="typed-authorization"></a>

### Typed authorization capabilities

Alice performing a project action and assigning Bob permission to perform it are different decisions. Both need current eligibility, but assignment also checks delegation authority and the recipient. [ADR-0067](../../../../docs/adr/ADR-0067-standardize-authorization-capabilities-with-typed-requests.md) gives both a common calling convention without combining their rules.

[`Authorizer[RequestType, ResultType]`](../../../../apps/backend/src/inframeld_backend/access/application/protocols/authorizer.py) declares the abstract keyword-only method `require_authorization(access, request)`. The family Protocol specializes request and result types. Concrete services and test doubles explicitly inherit their family and mark the method with `@override`. Inheriting this required behavior does not create an empty marker interface.

| Family | Request | Result | Existing consumer |
| --- | --- | --- | --- |
| `ActionAuthorizer` | `ProjectActionAuthorizationRequestDTO`: project and action selected by the trusted workflow. | `ProjectActionAuthorizationDTO`: matched organization and project. | `ProjectOperationAdmissionService` |
| `ProjectGrantAuthorizer` | `ProjectUseOnlyGrantAuthorizationRequestDTO`: project, recipient and action being delegated. | `ProjectGrantAuthorizationDTO`: matched scope and current project access revision. | `ProjectGrantChangeService` |

Requests are temporary frozen, slotted Access application DTOs, independent of business Commands and HTTP models. They add no persisted state. Field annotations establish neither existence nor permission. They carry no retry context, fingerprint or expected revision. The concrete authorizers keep their existing facts readers, visibility ordering and domain policies. `ActionAuthorizationService` converts its request into the existing `ProjectActionTargetDTO` for the reader. Shared eligibility still has one domain-policy owner.

Both consumers compare the returned project with the requested project before reservation or replay. A mismatch raises `RuntimeError`. After matching, use scope from authorization downstream and preserve the requested business input unchanged. The grant service owns rollback through its transaction manager. The admission helper never commits or rolls back on its own, and its caller retains transaction ownership.

Reuse the ordinary action family for another operation needing the same kind of exact project-action check. The trusted application workflow chooses the required action, rather than taking a permission selector from HTTP input. Add another family when a decision needs materially different inputs or rules. The shared Protocol standardizes signatures and does not execute policy, force a caller to authorize or make a result a reusable permission certificate. Behavioral denial, scope-mismatch, replay and database tests establish the actual boundaries. This qualifies two existing consumers, not a second complete product write workflow.
