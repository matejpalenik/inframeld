# Upgrade deliberately

<a id="upgrade-deliberately"></a>

Migrations are an explicit operator action. The API checks schema compatibility at startup and refuses an incompatible database. Starting or restarting it never authorizes a migration.

<a id="deploy-credential-versioning-as-one-coordinated-cutover"></a>

### Deploy credential versioning as one coordinated cutover

Apply migration `0005_human_credential_versions` and deploy its matching backend together. Startup requires the supported revision. Existing human CLI tokens lack binding metadata and require one fresh sign-in. Browser sessions and application keys keep their existing contracts. No unversioned compatibility mode or mixed-version backend deployment is supported.

Persist credential version state with installation identity across restarts and backups. Do not prune it with cleanup history, downgrade its schema or restore an older security generation as a routine rollback. Missing state with recovery history requires repair, not silent initialization. [ADR-0072](../../adr/ADR-0072-version-human-cli-credentials-across-account-recovery.md) records this choice.

Future production ingress must keep Hydra administration private and expose only required OAuth/OIDC routes. Do not expose a generic Hydra administration proxy through Inframeld. Block external `/userinfo` if qualification confirms the selected CLI/library does not require it, and keep discovery/client behavior consistent with deployed routing. Containers on an internal network alone do not establish this restriction. The gateway and CLI remain delivery work.

<a id="understand-the-compatibility-boundary"></a>

<a id="compatibility"></a>

<a id="1-understand-the-compatibility-boundary"></a>

## CLI and runtime release pairing

[ADR-0095](../../adr/ADR-0095-support-matching-qualified-cli-and-runtime-releases.md) selects explicitly qualified matching CLI/runtime releases initially. Upgrade them as a coordinated pair. Development CLI builds claim no released runtime support. Offline version output identifies the supported pair when one has been qualified, but remote compatibility remains unverified until a backend version contract is delivered. Health and login success cannot replace that check. A decode failure never authorizes repeating a write.

## Understand the compatibility boundary

API and worker releases must be compatible with the same stored data. That includes the database **schema**, its tables, fields, and relationships.

Record explicit versions for three kinds of stored data:

| Versioned representation | What it describes |
| --- | --- |
| **Database schema** | The structure of application data in the database. |
| **Job payload** | The stored instructions and inputs the worker uses to execute a job. |
| **Artifact format** | The structure of stored outputs, such as processing results or manifests. A manifest records an inventory of artifacts or source identities. |

If a new worker cannot understand an older job format, it must reject it safely. Connecting successfully to PostgreSQL does not mean it can interpret every stored job.

<a id="migrations-have-one-execution-owner"></a>

### Migrations have one execution owner

A **migration** changes the database's structure or stored representation. The operator runs it through one explicit command or job. A database migration lock prevents two migrations from running at once.

On startup, API and worker check compatibility and refuse incompatible state. They must not each try to migrate the shared database.

<a id="perform-a-controlled-upgrade"></a>

<a id="upgrades"></a>

<a id="2-perform-a-controlled-upgrade"></a>

## Perform a controlled upgrade

Use this sequence for the initial supported upgrade:

1. **Stop accepting new work.** Put the installation into maintenance mode.
2. **Finish or safely stop current work.** Account for running requests and jobs, including vector writes and model calls whose outcome is unknown.
3. **Take a backup.** Follow the [coordinated backup procedure](backups.md#backup) before changing stored state.
4. **Run controlled migrations.** Use the operator-controlled application command and its database lock. Run any required Kratos/Hydra migrations through their supported mechanisms and designated owners, not competing startup migrations or custom writes to vendor tables.
5. **Start the matching release set.** Deploy compatible API, worker, Kratos, Hydra and account-UI versions for the resulting application and identity schemas, job payloads, artifacts and protocol configuration.
6. **Check before reopening.** Resume normal traffic only after the upgraded installation passes its required readiness checks.

**Stopping incoming requests does not cancel a request already sent to another service.** A vector store or model provider may still complete work after the application stops waiting for it.

Use the [Indexing recovery rules](../../../.agents/skills/inframeld-indexing/references/profiles-and-preparation.md) for uncertain vector writes and the [job rules](../../../.agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md) for provider calls. Maintenance mode alone does not establish whether remote work finished or whether repeating it is safe. Release qualification owns the tested release matrix, including identity migrations. Preserve the configured issuer, audience, official CLI client registration and principal mappings, and check fresh login under current permissions before reopening. An ordinary compatible upgrade follows normal expiry and revocation rules. It does not require clearing every session or saved CLI selection. Restoring an older backup instead invokes [the stricter recovery rules](restore.md#restrictions), including independent invalidation of restored credentials. If an identity migration commits and readiness fails, remain in maintenance and use a qualified forward repair or coherent restore. Restarting older images is safe only when compatibility with the resulting identity state has been demonstrated.

<a id="prefer-additive-changes-migrate-representations-in-stages-when-needed"></a>

<a id="prefer-additive-changes-and-migrate-representations-in-stages-when-needed"></a>

### Prefer additive changes and migrate representations in stages when needed

Prefer changes that preserve the old representation while introducing the new one. For example, add an optional column before removing a field that existing work still uses. This is an **additive change**.

When old and new representations need to coexist, use the following sequence:

| Phase | What happens |
| --- | --- |
| **Expand** | Add the new representation while keeping the old one available. |
| **Backfill** | Populate the new representation for existing records using bounded, resumable work. |
| **Verify** | Check the converted data before relying on it. |
| **Switch** | Change the application to use the new representation. |
| **Remove later** | Remove obsolete fields in a later release, not as part of the initial expansion. |

Convert existing data in limited-size steps and record progress so an interruption does not restart the whole conversion. This is what “bounded, resumable backfill” means.

Use this staged approach when old and new representations need to coexist. Updating both on every write, called **dual-writing**, is unnecessary when a maintenance window can handle the conversion safely.

<a id="treat-application-rollback-as-a-compatibility-decision"></a>

### Treat application rollback as a compatibility decision

An **application rollback** returns to an earlier Inframeld software version, usually by starting its earlier container image.

It is safe only if that version supports the database schema, saved jobs, and artifact formats now present. The fact that the old container starts is not enough.

A **down migration** attempts to reverse a schema change. Do not assume it preserves data, or delete newer data merely to make an older application run.

A destructive change needs a separate migration review and a tested restore point, meaning a backup from which recovery has been demonstrated.

<a id="a-rag-pipeline-rollback-is-a-different-operation"></a>

### A RAG pipeline rollback is a different operation

A **retrieval-augmented generation (RAG) pipeline** retrieves document evidence and uses it to generate an answer. A Deployment selects which pipeline version serves requests.

Rolling back a pipeline changes those pointers. It does not downgrade the Inframeld application, reverse a database migration, or solve an incompatibility between application code and persisted data.

<a id="worked-example-an-optional-field-can-still-affect-rollback"></a>

### Worked example: an optional field can still affect rollback

Suppose **application release 2** adds an optional field used by new jobs. These release numbers refer to Inframeld software, not pipeline versions.

During maintenance, the migration adds the column **before release 2 starts**. The matching API and worker can then use it for release-2 jobs.

Returning to release 1 is safe only if it can ignore the added column and avoid executing release-2 jobs it cannot understand. An optional column alone does not prove rollback is safe. Check job and artifact compatibility as well.

If compatibility is unknown, keep maintenance mode enabled. Restore through the documented procedure or ship a newer release that fixes the problem using the current stored state. The latter is a **corrective forward change**.

**Do not assume that removing the new column through a down migration will preserve the newer data or make its jobs safe to execute.**

<a id="maintainer-checks"></a>

<a id="8-maintainer-checks"></a>

## Maintainer checks

Use representative persisted jobs, source and artifact references, and Deployments. An upgrade test against an empty database alone does not exercise these compatibility requirements.

| Area | Required verification |
| --- | --- |
| **Upgrade** | Apply the upgrade against representative existing state and verify that the new API and worker can use it correctly. |
| **Migration ownership** | Verify migration locking and that API/worker startup cannot race to migrate the schema. |
| **Compatibility refusal** | Verify that incompatible startup is rejected and that the new worker safely rejects unsupported old job shapes. |
| **Backfill recovery** | Interrupt a backfill and verify that its bounded work can resume. |
| **Supported application rollback** | Exercise the claimed rollback path against persisted jobs, source/artifact references, and Deployments, not only the database schema. |
| **Restore** | Validate the documented restore procedure and the restore point required for destructive changes. |

These are acceptance conditions. The maintenance-upgrade approach is accepted, but implementation qualification has not yet been completed.
