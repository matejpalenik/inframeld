# ADR-0012: Controlled database and runtime upgrades

**Status:** Accepted — maintenance-upgrade baseline; implementation qualification pending.
**Revised:** 19 September 2026.
**Required approach:** Operator-controlled migrations and coordinated maintenance upgrades in production Docker Compose. Zero-downtime runtime upgrades are outside v1 scope.
**Related:** [Runtime deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md), [recovery](ADR-0013-minimal-hosted-observability-and-recovery.md).

## Context

Inframeld’s API handles incoming requests, while its worker executes background jobs. Both depend on stored data that survives a process restart or container replacement.

A new application release can change the database structure, the information stored in a job, or the format of a processing artifact. Updating the application image does not automatically make those existing records compatible with the new code. Returning to an older image does not automatically make newer records compatible with the old code either.

From first principles, **an application version is safe to run only when it understands the stored representations it needs to use**. Upgrades must therefore coordinate application code, database changes, and existing work—not simply restart containers.

For v1, we accept a documented maintenance window instead of requiring uninterrupted service during an upgrade. The priority is a controlled, testable procedure that preserves data and handles unfinished work safely.

## Decision

**Run database migrations through one operator-controlled command or job, protected by a database migration lock. Upgrade the API and worker together during a documented maintenance window, and reopen traffic only after compatibility and readiness checks pass.**

Prefer changes that preserve existing data and representations. Permit application rollback only when the older runtime supports the resulting database, job, and artifact versions. A rollback must not silently discard newer data.

### 1. Keep the API, worker, and persisted formats compatible

The API and worker share a versioned database schema and run from a compatible application image. A **schema** describes the database’s tables, fields, and relationships.

Database compatibility is only one part of the requirement. Make all three persisted-format versions explicit:

| Versioned representation | What it describes                                                                                                                            |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **Database schema**      | The structure of application data in the database.                                                                                           |
| **Job payload**          | The stored instructions and inputs the worker uses to execute a job.                                                                         |
| **Artifact format**      | The structure of stored outputs, such as processing results or manifests. A manifest records an inventory of artifacts or source identities. |

A new worker must safely reject an old job shape it does not support. Starting successfully against the database is not permission to guess how to interpret an unfamiliar job payload.

#### Migrations have one execution owner

A **migration** is a controlled change to the database’s structure or stored representation. Apply it through the explicit operator-controlled migration command or job, with a database migration lock preventing concurrent migration execution.

API and worker startup check compatibility and refuse an incompatible configuration. **Startup is a compatibility check, not an invitation for each process to run migrations.** They must not race to modify the shared schema.

### 2. Upgrade through a documented maintenance window

Use this sequence for the initial supported upgrade:

1. **Stop admission.** Stop accepting new application work. Admission is the point at which the application accepts an operation for execution.
2. **Finish or safely stop in-flight work.** Account for requests and jobs already running, including vector writes and model-provider calls whose outcomes may be uncertain.
3. **Take the documented backup.** Follow the recovery procedure in ADR-0013 before changing the stored state.
4. **Run the migration once.** Use the operator-controlled migration command and its database lock, not competing startup migrations.
5. **Deploy matching application images.** Start the compatible API and worker release against the resulting schema and persisted formats.
6. **Verify readiness before reopening traffic.** Reopen admission only after the upgraded installation passes its required checks.

**Stopping incoming requests does not cancel a request already sent to another service.** A vector store or model provider may still complete work after the application stops waiting for it.

Handle uncertain vector operations under [ADR-0004](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md) and uncertain provider/job operations under [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md). Maintenance mode is not evidence that those external operations failed or are safe to repeat.

### 3. Prefer additive changes; migrate representations in stages when needed

An **additive change** introduces something new while preserving the existing representation—for example, adding an optional column rather than immediately removing a field still in use.

When old and new representations need to coexist, use the following sequence:

| Phase            | What happens                                                                        |
| ---------------- | ----------------------------------------------------------------------------------- |
| **Expand**       | Add the new representation while keeping the old one available.                     |
| **Backfill**     | Populate the new representation for existing records using bounded, resumable work. |
| **Verify**       | Check the converted data before relying on it.                                      |
| **Switch**       | Change the application to use the new representation.                               |
| **Remove later** | Remove obsolete fields in a later release, not as part of the initial expansion.    |

**Bounded** means each backfill step handles a limited amount of work. **Resumable** means an interruption does not require starting the entire conversion again.

Do not require this coexistence strategy for every change. In particular, **dual-writing**—updating both representations whenever data changes—is not mandatory when the coordinated maintenance upgrade can handle the change safely without it.

### 4. Treat application rollback as a compatibility decision

An **application rollback** returns to an earlier version of Inframeld’s runtime, usually by deploying its earlier application image.

It is permitted only when that runtime supports the resulting schema, job-payload versions, and artifact-format versions. The fact that an old container starts does not establish that it can safely process the stored work.

Do not blindly reverse database migrations or drop newer data merely to make an older binary run. A **down migration** attempts to reverse a schema change; its existence does not prove that the reversal preserves data.

Destructive changes require a separately reviewed migration and a tested restore point: a backup state from which the documented recovery procedure has been validated.

#### A RAG pipeline rollback is a different operation

A **retrieval-augmented generation (RAG) pipeline** retrieves document evidence and uses it to generate answers. Its Deployment pointers select which pipeline version serves requests.

Rolling back a pipeline changes those pointers. It does not downgrade the Inframeld application, reverse a database migration, or solve an incompatibility between application code and persisted data.

### 5. Worked example: an optional field can still affect rollback

Suppose **application release 2** adds an optional field used by new jobs. These release numbers refer to Inframeld software, not pipeline versions.

During maintenance, the migration adds the column **before release 2 starts**. The matching API and worker can then use it for release-2 jobs.

Later, the operator considers returning to release 1. That is safe only if release 1 can ignore the added column and does not consume release-2 jobs whose payloads it does not support. The general schema/job/artifact compatibility rule still applies: the column being optional is not sufficient evidence of a safe rollback.

If compatibility is not established, keep maintenance mode enabled. Either restore through the documented procedure or ship a **corrective forward change**: a newer release that fixes the problem while working with the current stored state.

**Do not assume that removing the new column through a down migration will preserve the newer data or make its jobs safe to execute.**

### 6. Test upgrades and supported rollback before release

Use representative persisted jobs, source and artifact references, and Deployments. An upgrade test against an empty database alone does not exercise these compatibility requirements.

| Area                               | Required verification                                                                                                                |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **Upgrade**                        | Apply the upgrade against representative existing state and verify that the new API and worker can use it correctly.                 |
| **Migration ownership**            | Verify migration locking and that API/worker startup cannot race to migrate the schema.                                              |
| **Compatibility refusal**          | Verify that incompatible startup is rejected and that the new worker safely rejects unsupported old job shapes.                      |
| **Backfill recovery**              | Interrupt a backfill and verify that its bounded work can resume.                                                                    |
| **Supported application rollback** | Exercise the claimed rollback path against persisted jobs, source/artifact references, and Deployments—not only the database schema. |
| **Restore**                        | Validate the documented restore procedure and the restore point required for destructive changes.                                    |

These are acceptance conditions. The maintenance-upgrade approach is accepted, but implementation qualification has not yet been completed.

## Consequences

### Positive

- **Schema changes have one controlled execution path.** The migration lock and explicit command prevent API and worker startup from competing to change the database.
- **Upgrades account for persisted work as well as code.** Explicit schema, job, and artifact versions make compatibility checks part of the upgrade and rollback procedure.
- **V1 avoids unnecessary always-online migration machinery.** A coordinated maintenance window can handle suitable changes without mandatory dual-writing, while staged backfills remain available when representations must coexist.

### Negative

- **Upgrades interrupt normal service.** The operator must arrange a maintenance window, handle in-flight work, take the required backup, and verify readiness before reopening traffic.
- **Reverting an image is not always a safe recovery option.** Newer persisted data or jobs can prevent application rollback, requiring a documented restore or corrective forward change instead.
- **Compatibility and recovery need explicit testing.** Migration locking, resumable backfills, supported rollback paths, and destructive-change restore points add implementation and release work.

## Alternatives considered

The source does not record a separate comparative assessment. The following approaches are excluded or not required by this decision.

### Run migrations automatically from every API or worker startup

**Ruled out.** These processes share a schema and must not compete to migrate it. Startup checks compatibility; one operator-controlled command or job applies the migration under a database lock.

### Require zero-downtime upgrades and dual-writing for every change

**Not required for v1.** The supported baseline uses a documented maintenance window. Staged coexistence is available where needed, but dual-writing is not imposed on changes that maintenance can safely coordinate.

Kubernetes, a rolling-deployment controller, and multi-region coordination are not dependencies of this upgrade process.

### Automatically reverse migrations when reverting the application image

**Ruled out as a blanket rollback strategy.** The older runtime must support the resulting schema, jobs, and artifacts. Reversing a migration can remove newer data without resolving those compatibility requirements.

Use a supported runtime rollback, a validated restore, or a corrective forward change as appropriate. Destructive migrations remain separately reviewed and require a tested restore point.

## References

| Reference                                                                                | Responsibility                                                                            |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| [ADR-0011: Runtime deployment](ADR-0011-hosted-vercel-and-aws-deployment-profile.md)     | The production Docker Compose installation and coordinated application-release procedure. |
| [ADR-0013: Recovery](ADR-0013-minimal-hosted-observability-and-recovery.md)              | The documented backup and restore procedure used during upgrades and recovery.            |
| [ADR-0004: Vector writes](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md)      | Handling vector operations whose external outcomes are uncertain.                         |
| [ADR-0007: Durable jobs and recovery](ADR-0007-durable-jobs-idempotency-and-recovery.md) | Safe job handling, retries, and uncertain provider outcomes.                              |
