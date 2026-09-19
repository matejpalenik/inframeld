# ADR-0011: Production single-server Docker Compose deployment

**Status:** Accepted — Docker Compose, selected stores, and baseline backup/restore. Runtime and operational qualification remain pending.
**Date:** 17 September 2026.
**Revised:** 19 September 2026.
**Required approach:** A production-grade, single-server open-source installation, with private durable stores, enforced security boundaries, and documented recovery.
**Source:** [Canonical architecture guide](../ARCHITECTURE.md).
**Related:** [Vector storage](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md), [identity and authorization](ADR-0005-api-enforced-tenancy-and-authorization.md), [durable jobs](ADR-0007-durable-jobs-idempotency-and-recovery.md), [parser isolation](ADR-0010-secure-document-ingestion-boundary.md), [database migrations](ADR-0012-backward-compatible-database-migrations.md), [operations and recovery](ADR-0013-minimal-hosted-observability-and-recovery.md), [materializations](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md).

## Context

Users first try Inframeld locally, then run the same product in a company sandbox. They need a clear release workflow, durable data, and reasonable security without first provisioning a hosted software platform. One developer must be able to maintain both the application and its supported installation.

From first principles, **starting the application, preserving its data, and recovering after failure are different responsibilities**. Replacing a container must not discard the database. Keeping that database in a persistent volume, however, does not protect it from loss of the host disk. Production deployment therefore includes security controls, resource limits, upgrades, and tested backup/restore—not just a command that starts containers.

The supported target is a **documented and tested single-server installation with explicit limits**. It does not promise uninterrupted service during host failure, automatic failover, or million-document vector workloads on a small machine.

This decision completely replaces the earlier Vercel/AWS private-pilot plan. The legacy filename, `ADR-0011-hosted-vercel-and-aws-deployment-profile.md`, remains only to preserve existing links. Docker’s [production Compose guidance](https://docs.docker.com/compose/how-tos/production/) is the recorded reference for single-server production use and production-specific configuration.

## Decision

**Ship Inframeld v1 as an open-source application deployed on one Linux server using Docker Engine and the Compose v2 plugin. Use PostgreSQL for authoritative state, Chroma for vector search, SeaweedFS for S3-compatible artifacts, and Kratos for human identity and sessions.**

Separate processes protect request handling, background execution, and document parsing. They do not create independently owned business microservices.

SeaweedFS, the S3 artifact interface, Kratos, and baseline backup/restore are settled choices. The exact runtime configuration and operating limits still need qualification: testing the assembled installation against its requirements. ADR-0013’s backup approach, cadence, maintenance window, retention, and recovery objectives remain provisionally accepted planning estimates, not measured guarantees.

### 1. Use the same deployment model for trials and production

Each Inframeld release must identify its tested Linux host/runtime range, dependency versions, and exact image digests. An **image digest** identifies specific container-image content rather than a tag that can later point somewhere else.

Local Docker Desktop can provide a trial environment. The Linux production security checks still govern release qualification; local convenience does not establish that those checks have passed.

No AWS, Cognito, Vercel, hosted Chroma, cloud secret manager, or cloud infrastructure account is required. An **S3-compatible API** is an object-storage protocol interface. Using that interface—or an S3 source connector—does not require deploying Inframeld on AWS.

Custom OpenAI-compatible model endpoints remain available in **open-source software (OSS)**. All model calls, including evaluation, use the application’s `ModelGateway` boundary.

Kubernetes support, Terraform for a hosted platform, multi-host orchestration, and automatic horizontal scaling are deferred. A future **Enterprise Edition (EE)** deployment may use Chroma Cloud and cloud-hosted Kratos or Ory Network without changing domain ownership or replacing the identity technology. These possibilities are not dependencies of v1.

### 2. Give each runtime component one clear responsibility

An **ingress** is the entry point for incoming application traffic. **TLS** protects HTTPS connections. An **artifact** is stored content such as an original document, processing output, or manifest; a manifest records an inventory of artifacts or identities. **Vectors** are numerical representations used to search for relevant document excerpts.

| Component                                | Responsibility and exposure                                                                                                                                                                                                                   |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **HTTPS ingress**                        | The only published application entry point. Terminates TLS, routes web/API requests and Kratos’s public endpoints, and enforces request-size/time bounds. Trust forwarded headers only from configured proxies, not arbitrary callers.        |
| **Production-built Next.js web service** | Runs Studio, the browser interface, and its server-side session/proxy integration. Do not use a development server in the production profile.                                                                                                 |
| **Python API**                           | Handles admission, authorization, queries, and release commands. Admission means durably accepting requested work. Database and vector services need no public ports.                                                                         |
| **Python worker**                        | Runs the same application release/image as the API through a different command. Executes bounded durable jobs from PostgreSQL. Initially, only one worker is supported; vector mutation ownership follows ADR-0004.                           |
| **Isolated parser service**              | Converts untrusted documents using ADR-0010’s per-attempt sandbox. Has no network, credentials, general artifact volume, or Docker socket. Its only worker connection is a private IPC socket. IPC means interprocess communication.          |
| **PostgreSQL**                           | Holds authoritative application state, jobs, permissions, and operation records on durable storage. Accessible only privately. Kratos uses a separate database and database role on the same instance, with separately controlled migrations. |
| **Chroma server**                        | A private HTTP service with its own durable volume. API and worker use its client API, not a shared embedded persistence directory.                                                                                                           |
| **SeaweedFS artifact storage**           | A private S3-compatible service on durable storage behind the application-owned artifact interface. Its master, volume, filer, and S3 roles fit in one process/container; their responsibilities are explained below.                         |
| **Kratos identity service**              | Self-hosted human identity and sessions, integrated with Inframeld-owned account screens. Administration remains private. A local trial needs no cloud identity account, and selecting Kratos does not implicitly include Hydra.              |

Kratos also supports the selected deployment-level external **OpenID Connect (OIDC)** sign-in in OSS. OIDC lets the installation use a configured external identity provider. Inframeld supplies scoped opaque CI/integration credentials under ADR-0005; these application credentials are not a reason to add another identity issuer.

#### PostgreSQL delivers background jobs

The worker polls PostgreSQL for eligible work, claims bounded jobs, and records progress and recovery evidence. There is no mandatory queue broker or queue-outbox dispatcher. An outbox dispatcher would deliver messages recorded for external delivery; it is not needed merely because background work exists.

**A process restart does not prove that an external operation failed.** A provider might have completed a call whose response was lost. ADR-0007 defines safe retries and how to represent uncertain outcomes.

### 3. Reuse these processes for MCP, evaluation, and generated clients

The additional client and evaluation capabilities do not each need another service:

| Capability                              | Where it runs                                                                                                                                                                                                                                                                                |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **First-party MCP**                     | The Model Context Protocol adapter mounts the official Python SDK inside the existing API process. It reuses application operations and authorization, adding no container, store, or identity issuer. ADR-0018 defines the accepted transport/client profile and its pending qualification. |
| **OpenEvals**                           | A library inside the worker, with model calls through `ModelGateway` and configurable Luna as the initial judge. A judge is a model used to evaluate an answer. LangSmith, Langfuse, and exporters are deferred.                                                                             |
| **Studio’s official TypeScript client** | A generated build artifact used by Studio, not another deployed service. An SDK is a software development kit providing client operations.                                                                                                                                                   |

These placements keep the additional interfaces within the existing runtime rather than creating more deployed services.

### 4. Enforce parser isolation in the production installation

[ADR-0010](ADR-0010-secure-document-ingestion-boundary.md) is the controlling specification for parsing. This deployment must enforce it, not merely label the parser as a separate service.

The outer parser container uses `network_mode: none`, a read-only root filesystem, bounded resources, and dropped capabilities. It has no privileged mode or shared host namespaces. Linux capabilities are individual privileges; namespaces separate a process’s view of operating-system resources.

The worker streams one admitted input through a narrow **Unix-domain socket**, a local communication endpoint, and receives bounded output. The parser cannot list or read the artifact store.

#### Isolate each conversion from the supervisor and other attempts

Inside the service, a trusted supervisor starts each conversion in a fresh Linux sandbox with private user, process-ID (PID), mount, and network namespaces. Expose only read-only runtime/model assets, that attempt’s input, and private bounded temporary output.

The parsing child cannot see the supervisor’s IPC socket or another attempt’s files. Close inherited IPC descriptors—the handles to existing communication channels—so hiding a socket path does not leave an open connection available.

The supervisor enforces elapsed-time, output, and process limits and terminates the entire attempt on failure. **A normal Python subprocess or a private Docker network alone is insufficient.**

#### Unsupported isolation means failed readiness, not weaker security

The release must demonstrate that the unprivileged sandbox works with the tested kernel, container runtime, and security profile. If it does not, startup/readiness fails with an actionable configuration error. Do not silently disable isolation or grant broad host privileges to get parsing running.

Linux containers share the host kernel. This boundary limits the consequences of parser compromise; it does not provide virtual-machine isolation or prove protection from kernel vulnerabilities.

Pin model assets and include them in the release, or provision them through an operator-controlled process before jobs run. Parsing must not download arbitrary code or models at runtime.

### 5. Restrict access and resources for the whole installation

| Boundary                | Production requirement                                                                                                                                                                     |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Public exposure**     | Publish only the intended HTTPS ingress. Keep PostgreSQL, Chroma, artifact internals, identity administration, and parser IPC private.                                                     |
| **Networks and mounts** | Give services only the network attachments and filesystem mounts they need. The web service does not need data-volume access.                                                              |
| **Runtime privileges**  | Pin images by release and digest, run application services as non-root, drop unnecessary capabilities, prohibit Docker socket mounts, and use read-only root filesystems where compatible. |
| **Resource use**        | Explicitly limit CPU, memory, process count, and temporary disk use.                                                                                                                       |
| **Readiness**           | Verify usable dependencies and required security controls. A health check is not an authorization check and does not replace permission enforcement on requests.                           |

The operator controls the host, Docker daemon, filesystem permissions, TLS material, outbound networking, and backups. These responsibilities remain even when Compose starts the services together.

Host full-disk encryption and encrypted off-host backups protect stored data when it is offline. They do not hide plaintext from a compromised running service or a host administrator.

### 6. Separate infrastructure secrets from saved provider credentials

**Compose secret mounts and encrypted application credential storage serve different purposes.**

| Secret category                           | Storage and access                                                                                                                                                                                                        |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Infrastructure/bootstrap material**     | Protected operator-supplied files mounted only into the services that need them through service-specific Compose secrets. Bootstrap material supports the installation’s initial trusted setup.                           |
| **Application-entered model credentials** | Authenticated ciphertext in PostgreSQL using PyNaCl, as selected in ADR-0020. Authenticated ciphertext combines encryption with integrity checking. Users must be able to save these credentials through the application. |
| **Persistent root encryption key**        | Supplied separately and mounted only into the API and worker. It is not a credential that every container receives.                                                                                                       |

Compose mounts secrets into selected containers; **it is not an encrypted secret-management service**. Mounted provider files alone do not satisfy the onboarding requirement for persistent application-entered credentials.

No cloud secret manager or OpenBao service is selected. Never put secret values in tracked Compose files, image layers, job payloads, telemetry, or response replay records. The recorded reference for mount behavior is [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/).

### 7. Access artifacts through a small, private S3 adapter

**SeaweedFS is the single supported v1 S3 implementation.** Its object server ultimately stores data on host disks, but API/worker application code accesses that data through an S3 adapter behind `ArtifactStore`.

`ArtifactStore` is the application-owned interface for storing and retrieving artifacts. An adapter translates that interface into storage operations. Domain objects must not expose buckets, object keys, or storage SDK types. This preserves document and release ownership if a compatible cloud object store is introduced later.

Give API/worker **scoped service credentials**, not an administrative root key. Browsers and project integrations must use Inframeld’s authorized upload/download routes. Giving them bucket credentials would bypass the application’s document-group policy.

S3 identity integration, public bucket access, user-managed bucket policies, and a separate object-storage administration product are not required.

#### Implement only the required storage operations

| Requirement           | Expected behavior                                                                                                                                                                                                                    |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Streaming**         | Stream immutable source, processing, and manifest bytes. Generate opaque keys on the server, never from uploaded paths. An opaque key has no caller-controlled filesystem meaning.                                                   |
| **Operation subset**  | Support `PutObject`, `GetObject`, `HeadObject`, bounded `ListObjectsV2`, and `DeleteObject`, with verified size/checksum behavior. These write, read, inspect, list, and delete objects.                                             |
| **Multipart uploads** | Enable multipart operations only when the selected artifact bounds require them. If enabled, clean up incomplete uploads.                                                                                                            |
| **Publication**       | Publish the PostgreSQL artifact reference only after the object upload is complete and verified. A failed upload cannot become a successful document or materialization reference. A materialization is a prepared searchable index. |
| **Checksums**         | Never assume an object `ETag` is always a content checksum. Verify the selected server/SDK behavior.                                                                                                                                 |
| **Compatibility**     | Pin and test endpoint addressing, TLS/customer certificate-authority trust, request signing, and checksums. “S3-compatible” does not mean every AWS extension exists.                                                                |
| **Retention**         | Storage lifecycle rules must not expire objects referenced by retained current, candidate, or previous releases. Application retention/deletion owns those decisions.                                                                |

#### Upload immutable objects, then publish their references

Use immutable attempt-specific upload keys to avoid concurrent overwrites. An **attempt** is one recorded execution of work. After verification, conditionally publish the selected reference in PostgreSQL.

```text
Upload under a new attempt-specific object key
    -> Verify the completed object
        -> Conditionally publish its reference in PostgreSQL
```

A successful upload followed by an application crash may leave an unreferenced object for bounded cleanup. Retrying must not replace an already-published artifact with different bytes.

An unresolved upload can also finish **after cleanup**, leaving a late orphan: an object with no live application reference. One absence check does not prove final physical erasure while a write may still complete. Preserve attempt and tombstone evidence and qualify the store’s completion procedure. A tombstone records that an identity has been retired and must not become live again.

These are adapter and publication rules, not a new storage engine. Object versioning and same-host replication also do not replace off-host backup/restore.

### 8. Package SeaweedFS as one process with explicit durable paths

Use the same compact topology for local trials and production: **one SeaweedFS process with master, volume, local filer metadata, and S3 enabled**.

| SeaweedFS role | What must be accounted for                                                                                            |
| -------------- | --------------------------------------------------------------------------------------------------------------------- |
| **Master**     | The master’s state and its explicitly configured durable directory.                                                   |
| **Volume**     | Stored object chunks and their durable directory.                                                                     |
| **Filer**      | Metadata mapping object names and attributes to stored chunks. This metadata is separate from application PostgreSQL. |
| **S3**         | The private object API used by authorized backend clients.                                                            |

The packaging recommendation to qualify is `weed server -filer -s3`, with explicit durable paths, static backend credentials, and unused listeners disabled. It avoids another metadata database service, cluster orchestration, and multiple SeaweedFS containers.

**This is a recommendation to test, not an already-qualified production Compose file.**

#### Fix paths and disable unnecessary listeners

The source’s inspection of SeaweedFS 4.47 records these `server` options for qualification:

| Example setting                           | Purpose                                                       |
| ----------------------------------------- | ------------------------------------------------------------- |
| `-dir=/data/volume`                       | Explicit volume-data location.                                |
| `-master.dir=/data/master`                | Separate master-state location.                               |
| `-s3.config=/run/secrets/seaweed-s3.json` | Operator-supplied static S3 credential configuration.         |
| `-s3.port.iceberg=0`                      | Disable the Iceberg listener.                                 |
| `-s3.port.lance=0`                        | Disable the Lance listener.                                   |
| `-s3.iam=false`                           | Disable the optional S3 identity/access-management subsystem. |

Also disable WebDAV, SFTP, debug, and telemetry functionality. Set replication, volume-size/count limits, and free-space admission explicitly from the tested disk budget. These paths form part of the backup inventory; the table is **not a complete deployable command**. Recorded reference: [SeaweedFS 4.47 server options](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/server.go).

Configure one embedded `[leveldb2]` filer store in `filer.toml`, with `enabled=true` and `dir=/data/filer`. Disable other stores and persist the **whole `/data` tree**. Never let the process’s default working directory decide where persistent metadata goes.

This embedded metadata store does not require another database service, but it does create data that the backup must include. Recorded references: [filer store configuration](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/scaffold/filer.toml) and [LevelDB2 implementation](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/filer/leveldb2/leveldb2_store.go).

#### Do not substitute an unreviewed quick start

`weed mini` also combines the components. However, the recorded 4.47 inspection found that it starts an administration/maintenance-worker subsystem even with `-admin.ui=false`. WebDAV and additional S3 catalog listeners also need attention. It persists `mini.options` and can generate local **server-side encryption (SSE)** key files.

A generic mini quick start is therefore not the minimal secured configuration selected for qualification. Do not copy its default command/ports into production or introduce a second trial topology unnecessarily. Recorded reference: [tagged mini startup and persistence](https://github.com/seaweedfs/seaweedfs/blob/4.47/weed/command/mini.go).

#### Verify access control and actual durability

Only API/worker clients need the S3 interface. Keep master, volume, and raw filer endpoints off the public ingress and separated from untrusted services.

Explicit credentials and **negative authorization probes**—tests proving unauthorized requests are denied—are release prerequisites. A running S3 endpoint does not establish that authentication is enabled.

Pin and test write-flush/durability settings and recovery after interrupted writes. An acknowledged HTTP upload alone does not prove survival of sudden power loss. ADR-0013 contains the complete SeaweedFS backup inventory and coordinated stop/copy/restore proposal.

### 9. Operate the installation with visible limits and coordinated recovery

Provide redacted structured logs, bounded log retention, and visible job, error, latency, and disk signals. **Redaction** removes sensitive values; structured logs expose consistent fields for inspection rather than requiring an external observability platform.

Reject admission before the configured storage or work limits are exhausted. Monitoring must show backup age and failed restores. An external observability platform is optional.

#### Back up a matching set, not unrelated directories

Use a documented maintenance window for migrations, coordinated backups, and restore. The recoverable set includes:

| State                                    | Why it belongs in recovery                                                                                                                                               |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Application PostgreSQL state**         | Preserves application identities, permissions, jobs, operation records, and release state.                                                                               |
| **Kratos identity state**                | Restores identity/session data from its separate database alongside the installation.                                                                                    |
| **SeaweedFS artifact data and metadata** | Restores object bytes together with the master/filer state needed to locate and interpret them. An application PostgreSQL backup does not contain this storage metadata. |
| **Required Chroma persistence**          | Restores the numerical search data needed by retained materializations.                                                                                                  |
| **Required keys and configuration**      | Makes the restored state usable with the corresponding protected deployment material.                                                                                    |

Follow the selected stores’ supported consistent-backup procedures. Copying live database/vector files without a supported snapshot or **quiescence** protocol is insufficient. Quiescence means bringing the relevant activity to a controlled state in which the copy can be consistent.

Keep at least one operator-controlled backup **outside the host’s failure domain**, meaning it remains available when that host or its disk is lost. Document retention and the **recovery point objective (RPO)**, the intended limit on how much recent history may be lost, and rehearse restoration.

For example, a successful daily backup can still leave changes since that backup vulnerable to disk failure. That is an explicit recovery point, not zero data loss. **A named Docker volume survives container replacement, not loss of its host disk.**

#### Restore vectors; do not imply they can be reconstructed from manifests

The baseline restores required Chroma persistence together with application and S3 artifact state under ADR-0013. Manifests alone cannot recreate numerical vectors.

Product-level index reconstruction and retained numerical archives are deferred. Future recovery by re-embedding would need separately designed isolated numerical lineage: new numerical executions must not overwrite retained identities. Creating an ordinary new pipeline version does not, by itself, guarantee isolation or identical recovery.

Backup/restore is also separate from ordinary indexing retries in ADR-0004. A safe retry of captured vector bytes is not a substitute for restoring lost published storage.

### 10. Upgrade the application through an explicit maintenance sequence

An application release changes software and may change database structure. It is different from releasing a **retrieval-augmented generation (RAG)** pipeline, which retrieves source excerpts to help generate answers. A pipeline release changes the logical version serving those answers.

1. **Publish the release package.** Supply versioned Compose/configuration documentation and immutable application images, including API/worker compatibility and parser/model assets.
2. **Validate the installation inputs.** Check operator configuration, free space, secrets, TLS, identity, and artifact setup. Ship neither shared default credentials nor an unauthenticated production mode.
3. **Pause the required work and take a consistent backup.** Stop new mutations and jobs as required by the documented upgrade procedure, then take its specified backup.
4. **Run migrations explicitly once.** Use the dedicated migration command and privileges. API/worker startup must not independently race to change the database schema, its stored structure.
5. **Start the matching release and verify readiness.** Start the API, worker, parser, and web release. Check dependencies and security probes before reopening admission.
6. **Exercise the product workflow.** Test login, project scoping, upload/build/query, evaluation status, canary selection, candidate rejection, promotion, and rollback. Confirm retry and recovery status remain visible.

A **canary** tries a pipeline version with a selected portion of routing identities. Promotion and rollback move logical serving references; they do not migrate the application database.

Application-image rollback must respect schema compatibility under [ADR-0012](ADR-0012-backward-compatible-database-migrations.md). **A RAG Deployment rollback does not roll back the application database schema.**

### 11. Qualify the installation before making production claims

The following are release criteria, not tests completed by this record.

| Area                              | Required verification                                                                                                                                                                               |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Installation and identity**     | Install on a fresh machine and complete an authenticated local trial. Pin tested Kratos and SeaweedFS images before release.                                                                        |
| **Exposure and isolation**        | Verify production TLS, private ports, parser isolation, and required security/readiness controls.                                                                                                   |
| **Durable execution**             | Restart jobs and demonstrate the documented retry and uncertain-outcome behavior.                                                                                                                   |
| **Storage failures**              | Kill storage during upload, fill its disk, restart with acknowledged writes, and corrupt a test artifact. Partial writes must never become published references; checksum failures must be visible. |
| **Storage authorization**         | Prove unauthorized S3 access is denied rather than assuming credentials are enforced because the service starts.                                                                                    |
| **Recovery**                      | Back up and restore a consistent set, including filer metadata, volume bytes, Chroma, identity/application state, and required keys/configuration.                                                  |
| **Upgrades and product behavior** | Exercise controlled migrations and the release-loop smoke test, a short end-to-end check of the essential workflow.                                                                                 |

#### Measure this workload rather than borrowing a vendor result

To establish storage performance and reliability for Inframeld, fix hardware, object sizes, concurrency, checksum handling, sync/durability settings, and server/SDK versions.

Measure source upload/read, bounded manifests, repeated small-corpus updates, deletion, peak memory, disk amplification, and backup/restore time. **Disk amplification** is the extra storage consumed beyond the logical input. Inspect **p95 latency**, the 95th percentile of observed request duration, alongside throughput.

A large sequential-transfer result does not predict thousands of small manifest operations. Parsing, embedding, or Chroma may dominate total build time, but that remains an assumption until measured.

These are focused qualification tests, not a requirement to build a benchmark platform or a second object-store adapter. Million-document capacity is qualified separately under ADR-0004/0015; this deployment ADR adds no capacity guarantee.

#### What remains to be qualified

Retain ADR-0013’s provisionally accepted backup cadence, planned outage, retention, and recovery estimates. Qualify and refine them with exact image/configuration pins, supported host/runtime versions, disk limits, and the measured workload.

The unfinished work is **testing and refining the selected installation**, not reopening SeaweedFS, S3 compatibility, Kratos, or baseline backup/restore without a new decision.

## Consequences

### Positive

- **The same OSS product can move from a local trial to a company sandbox.** It requires no mandatory cloud infrastructure account or hosted platform, while retaining authentication, model-gateway access, and the in-app release workflow.
- **Process and storage responsibilities stay explicit.** The API and worker share one application release; parsing is isolated; PostgreSQL owns application state; Chroma and SeaweedFS expose private interfaces behind application boundaries.
- **Recovery and operational limits are part of the deliverable.** Versioned deployment instructions, resource bounds, controlled upgrades, and rehearsed backup/restore define what the supported installation must demonstrate rather than equating a successful startup with production readiness.

### Negative

- **One host remains one availability boundary.** Host loss interrupts service; containers, shards, and same-host replicas do not provide automatic failover. The operator maintains off-host backups, security updates, and the host itself.
- **S3 compatibility adds a real storage service.** SeaweedFS replaces the filesystem-only proposal and brings several logical components, persistent filer metadata, and durability/authentication settings that need coordinated protection.
- **The installation requires operational work and planned maintenance.** Secrets, TLS, host security, resource limits, migrations, backups, and restore tests remain operator/developer responsibilities. Exact pins and recovery estimates cannot be presented as qualified until tested.

## Alternatives considered

The source records the withdrawal of the cloud-pilot and filesystem-only plans, a comparison of SeaweedFS and RustFS, and the exclusions below. It does not establish a measured performance winner or a completed security/reliability audit.

### Keep the Vercel/AWS private-pilot plan

**Replaced.** The v1 deliverable is a production-grade single-server Compose installation. AWS, Cognito, Vercel, and cloud infrastructure provisioning are not prerequisites. The legacy filename is retained for links, not as a second supported deployment plan.

### Store application artifacts only through a filesystem adapter

**Withdrawn.** An S3-compatible artifact API is required. SeaweedFS may itself use host disks, but application code accesses artifacts through the selected S3 adapter and `ArtifactStore` boundary rather than a filesystem-only implementation.

### Use RustFS instead of SeaweedFS

**Not selected for v1.** The recorded rationale favors SeaweedFS as the more conservative operational starting point for this project: longer visible operating history and a compact S3 deployment. RustFS remains a credible alternative, but the source identifies additional qualification responsibility for the sole developer at the time of review.

#### Dated evidence behind the storage decision

The source records the following primary-source review on **19 September 2026**. These are historical observations preserved from that review, not a fresh verification or approved Inframeld image pins. No comparative benchmark, source-wide quality audit, security audit, restore rehearsal, or million-object test was performed.

| Criterion                      | SeaweedFS: recorded evidence                                                                                                                                                                                                                                                                    | RustFS: recorded evidence                                                                                                                                                                                                                               |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Release and license**        | [4.47](https://github.com/seaweedfs/seaweedfs/releases/tag/4.47), released **14 September 2026**, under [Apache-2.0](https://github.com/seaweedfs/seaweedfs/blob/4.47/LICENSE).                                                                                                                 | [1.0.0 GA](https://github.com/rustfs/rustfs/releases/tag/1.0.0), released **16 September 2026**, under [Apache-2.0 at that tag](https://github.com/rustfs/rustfs/blob/1.0.0/LICENSE). GA means general availability, not an alpha release.              |
| **Operating history**          | Public operational material predates RustFS GA, including a [2024 administration release](https://seaweedfs.com/posts/seaweed_admin_release/). Releases show continued fixes and contributors.                                                                                                  | The [GA announcement](https://rustfs.com/blog/announcing-rustfs-1-0-0-ga/) dates development from February 2024. Only three days of GA history existed at the recorded review; newness alone proves neither quality nor unreliability.                  |
| **Single-server options**      | [`weed mini`](https://github.com/seaweedfs/seaweedfs/wiki/Quick-Start-with-weed-mini) demonstrates combined master, volume, filer, and S3 roles. One process simplifies packaging, not the need to protect both data and metadata. Section 8 selects the `server` packaging profile to qualify. | [Installation guidance](https://docs.rustfs.com/en/installation) offers single-node single-/multiple-disk modes and distinguishes them from multi-node fault-tolerant deployment. One disk provides no disk redundancy.                                 |
| **Security evidence**          | The [security policy](https://github.com/seaweedfs/seaweedfs/blob/master/SECURITY.md) treats master, volume, and raw filer APIs as trusted-network components. Fixes target the latest release under that policy; private internal ports and explicit S3 credentials matter.                    | [GHSA-h956-rh7x-ppgj](https://github.com/rustfs/rustfs/security/advisories/GHSA-h956-rh7x-ppgj) records a historical hardcoded gRPC token affecting alpha.13–alpha.77, fixed in alpha.78. It is not evidence that GA 1.0.0 contains that vulnerability. |
| **Reliability/review signals** | 4.47 includes S3 policy/forwarded-host enforcement and faulty-media/copy fixes. Active corrections are useful evidence, while security-sensitive changes require careful upgrades.                                                                                                              | The 1.0.0 release lists crash/healing coverage. [Release assets](https://github.com/RustFS/RustFS/releases) include software bills of materials (SBOMs) and provenance information. Their presence does not prove coverage of every failure case.       |
| **Performance**                | Its [S3 benchmark page](https://github.com/seaweedfs/seaweedfs/wiki/S3-API-Benchmark) is upstream-produced; its small-file layout may help some workloads. No result was reproduced for this MVP.                                                                                               | No comparable RustFS-versus-SeaweedFS result was established for the same Inframeld workload, machine, and durability settings. Implementation language alone does not establish faster object operations.                                              |

The table preserves the review’s evidence and its limits; it is not a completed qualification of either product for Inframeld.

#### Limit the reasons attributed to the selection

SeaweedFS has a broad, actively changing codebase and several logical components. Its quick start does not establish safe credentials, a tested backup, or durability under disk failure. Protecting filer metadata and volume bytes together is mandatory, and the selected layout still needs a clean-host installation and restore rehearsal.

RustFS’s installation page, as recorded, both offers single-server production paths and labels single-node topology examples as non-critical, reserving stronger fault-tolerance descriptions for multi-node deployment. That guidance needs interpretation and testing for this use case; it is not proof that every single-node RustFS deployment is unsuitable.

The source also records a narrow documentation-review issue: in [issue 456](https://github.com/rustfs/rustfs/issues/456), a maintainer acknowledged AI-assisted documentation advertising an unavailable Helm setup. This establishes a documentation review failure, not how much production code was AI-generated or whether generated code caused storage defects. The selection does not depend on those unsupported allegations, star counts, vendor deployment counts, or implementation language.

Both inspected tags use Apache-2.0. Neither current license guarantees future licensing. Preserve the small S3 boundary, record the distributed image/license versions, and avoid proprietary-only storage capabilities. **MinIO remains excluded and is not reconsidered here.**

### Add a distributed storage or orchestration stack now

**Not required.** Neither object store provides host availability merely by running in Compose. Multiple replicas or erasure-coded fragments on one physical host cannot survive losing that host. Erasure coding distributes data and recovery information across fragments; those fragments still need independent failure boundaries to survive host loss.

Use only SeaweedFS’s required S3 surface, protect its internal APIs, and qualify the selected storage path. Do not enable distributed clustering, experimental engines, FUSE filesystem mounts, Iceberg, advanced identity federation, or every upstream feature.

Similarly, multi-host orchestration, Kubernetes, automatic horizontal scaling, and a mandatory queue broker/outbox dispatcher are outside the selected v1 installation. Resource sizing and tested recovery come before adopting distributed complexity.

## References

| Reference                                                                             | Responsibility                                                                                                  |
| ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| [Canonical architecture guide](../ARCHITECTURE.md)                                    | Overall product architecture and runtime ownership.                                                             |
| [ADR-0004](ADR-0004-postgresql-source-of-truth-and-shared-chroma.md)                  | Chroma ownership, immutable vector writes, safe retries, and capacity qualification.                            |
| [ADR-0005](ADR-0005-api-enforced-tenancy-and-authorization.md)                        | Kratos, external sign-in, application credentials, and authorization.                                           |
| [ADR-0007](ADR-0007-durable-jobs-idempotency-and-recovery.md)                         | PostgreSQL jobs, retry limits, and uncertain external outcomes.                                                 |
| [ADR-0010](ADR-0010-secure-document-ingestion-boundary.md)                            | Required parser service and per-attempt sandbox.                                                                |
| [ADR-0012](ADR-0012-backward-compatible-database-migrations.md)                       | Controlled migrations and application-image/schema compatibility.                                               |
| [ADR-0013](ADR-0013-minimal-hosted-observability-and-recovery.md)                     | Provisional operating objectives, complete backup inventory, consistent restore, and deferred reconstruction.   |
| [ADR-0015](ADR-0015-profile-specific-index-materializations-and-pipeline-bindings.md) | Profile-specific materializations and pipeline bindings.                                                        |
| [ADR-0018](ADR-0018-first-party-mcp-adapter.md)                                       | First-party MCP’s client/transport profile and pending qualification.                                           |
| ADR-0020                                                                              | Persistent application-entered credentials, encrypted PostgreSQL storage, and the separately supplied root key. |

The Docker documentation and SeaweedFS/RustFS source, release, licensing, and security links are retained beside the decisions and recorded observations they support.
