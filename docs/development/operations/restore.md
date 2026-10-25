# Restore

<a id="disaster-restore-requires-reconciliation-before-replay"></a>

### Disaster restore requires reconciliation before replay

A backup contains records only up to its capture time. Restoration can therefore lose later accepted work and completion records. The declared **recovery-point window** describes how much recent history may be missing.

For example, a job may be `queued` in the backup and have made a paid provider call before the failure. Restoring that backup makes the old queued state visible again. **It does not prove that the later call never happened.**

Before restarting provider-capable jobs or replaying builds, evaluations, or releases, follow [recovery reconciliation](upgrades.md). This means using the evidence that remains to decide what can safely run despite the missing history.

Do not promise deduplication or exactly-once external effects for history absent from the restored backup.

<a id="preserve-restrictions-after-restoration"></a>

<a id="restoration"></a>

<a id="5-preserve-restrictions-after-restoration"></a>

## Preserve restrictions after restoration

The supported restore procedure must account for restrictions imposed **after** the selected backup was taken.

For example, restoring a backup from before a document was deleted must not make that document available again. Restoring an older group membership must not restore permission that was subsequently revoked.

[Recovery](upgrades.md) proposes an operator's off-host record of restrictive changes and deletions. Restoration invalidates old sessions and credentials and keeps access closed where the record is incomplete. This procedure still needs testing and refinement. It does not require building an automatic journal service.

Keep affected scopes closed until current restrictions and the required treatment of deleted content have been established. A restored database’s historical state is not sufficient authority to reopen access.

Document when backups expire and what that means for deletion. **A deletion request does not immediately change every immutable backup.** Report live-store cleanup separately from backup copies that remain under their retention policy.

<a id="reapply-restrictions-before-reopening"></a>

<a id="restrictions"></a>

<a id="6-reapply-restrictions-before-reopening"></a>

## Reapply restrictions before reopening

A backup contains historical permissions and deletion state. Suppose Monday’s backup allows Bob to read HR documents, and that access is removed on Tuesday. Restoring Monday must not authorize Bob again.

The same problem applies to deleted documents, disabled accounts, narrowed integration scope, revoked keys, and retention periods that have since expired. **A complete data restore is necessary, but not sufficient, for safe reopening.**

<a id="keep-a-restrictiondeletion-register-outside-the-server"></a>

### Keep a restriction/deletion register outside the server

The provisional procedure names one installation operator to maintain an **access-restriction/deletion register** in protected company storage outside the server. It is a small record of restrictions that recovery must reapply, not a new event-sourcing service.

Before applying a restrictive change, project administrators record its request. The operator records the affected scope, stable user, credential, or document IDs, intended restriction, time, request/completion status, and reviewer.

Record retention policies and their effective dates too, so recovery can reapply automatic expiry. Keep each entry as long as any retained backup might need it. Monday's copy of the register cannot establish what changed on Tuesday.

Audit exports can help, but a daily export from the failed host cannot prove that every later change survived. The operator must establish that the evidence covers the selected backup cut through the incident, including outstanding requests and every administrator who could change access.

This manual procedure can fail through human error. If maintaining it is impractical, a separate decision could introduce a narrowly scoped automatic off-host record. Do not quietly assume that such a system already exists.

<a id="apply-current-security-before-reads-jobs-or-credential-reissue"></a>

### Apply current security before reads, jobs, or credential reissue

Keep public access closed while applying these checks:

| Area | Required restore behavior |
| --- | --- |
| **Human sessions and CI/integration credentials** | Invalidate restored Kratos browser sessions, Hydra access/refresh grants and Inframeld application credentials through their qualified owning mechanisms. Confirm each outcome independently. Success in one system does not prove cleanup in another. Permit fresh login or fresh scoped application credentials only after authorization review. CI credentials are those used by authorized automation. |
| **Accounts and local login credentials** | Review disabled identities and account-security changes. Where current credentials cannot be established safely, require controlled recovery/reset before enabling the account. |
| **Document and integration access** | Reapply narrower memberships, document allowlists, and integration ceilings, the maximum document scope an integration may use. |
| **Deletion and retention** | Reapply newer deletion tombstones and current retention expiry before retrieving or releasing content. |
| **Queued work** | Do not execute normal queued work under a historical authorization decision. Review it through [restore classification](#restore). |

**Missing restriction evidence does not mean there were no restrictions.** Keep affected projects, data, or accounts inaccessible. If the affected scope cannot be identified, keep the entire installation inaccessible.

An authorized person responsible for the affected scope must review retained content and reapprove current permissions before reopening. If deletion status is uncertain, record an explicit decision about that content. Requiring fresh login or invalidating credentials does not establish whether a document was deleted after the backup.

The four-hour recovery target is conditional on this reconciliation. It may be missed safely rather than met by reopening uncertain access.

<a id="restore-privately-and-classify-unfinished-work"></a>

<a id="restore"></a>

<a id="7-restore-privately-and-classify-unfinished-work"></a>

## Restore privately and classify unfinished work

1. **Isolate recovery.** Record the incident and select a completed backup. Keep public ingress, jobs, and provider calls disabled. Establish that the old instance cannot resume serving or writing. Changing DNS alone does not stop an old process.
2. **Restore the matching set.** Verify the encrypted backup and manifest, recover the required keys, and restore every component to its recorded path with correct ownership. Use matching supported images and schema versions. Do not combine recovery with an untested upgrade or create new SeaweedFS volume IDs over restored data.
3. **Check stores privately.** Verify the application, Kratos and Hydra databases with their matching configuration/key material. Preserve issuer/client and Kratos-to-principal identity mappings. Verify SeaweedFS namespace-to-volume references/checksums and Chroma dependencies. In limited-size batches, check artifact references and current, candidate, and previous Deployment pointers. Keep missing dependencies unavailable. Do not silently replace lost vectors with a new embedding call or missing identity state with a new installation.
4. **Reapply current restrictions.** Follow the [security review](#restrictions), then test both allowed and denied human/integration access. Anonymous object access and internal administrative endpoints must remain inaccessible. Test local login and any configured OIDC login using current settings.
5. **Review unfinished work.** Preserve original statuses as evidence. Identify safe resumptions and place uncertain work that can call a provider into `recovery_required`. A restored `queued` flag is not permission to execute it. The next section explains why.
6. **Check the application before reopening.** Query a known retained release and inspect its authorized evidence. During isolated rehearsal, try a safe release transition and rollback. Verify gateway routing, current document permissions, deleted-content exclusion, and idempotency. Record backup age, data loss, phase timings, checks, and exceptions. Reopen only validated scopes, then resume normal backups.

A stored object without a published application reference is still an orphan, not an admitted document. An interrupted candidate is still unfinished. Before using any published record, establish that its required data exists.

<a id="do-not-replay-uncertain-work-just-because-its-completion-was-lost"></a>

### Do not replay uncertain work just because its completion was lost

A job marked `queued` at the backup cut may have called a model and completed afterward. Restoring the backup loses that later completion record, not necessarily the provider’s execution or charge.

For example:

```text
At the backup cut: job J is queued
After the cut:     J calls a model and completes
After host loss:   restore shows J as queued again
```

**The restored record cannot prove that the model call never happened.** Unless the remaining work is positively known to be safe, put restored unfinished work that can call a provider into `recovery_required`. Keep its original backup status as evidence rather than replacing the history with the new classification.

Repeating a saved vector insertion can be safe because its exact numbers are already captured. Follow the [Indexing retry checks](../../../.agents/skills/inframeld-indexing/references/profiles-and-preparation.md). A new model call to recover a lost answer does not have that same guarantee.

Resume only work whose inputs, current permissions, and required retry payloads remain intact under the normal protocol.

<a id="lost-idempotency-history-limits-duplicate-detection"></a>

### Lost idempotency history limits duplicate detection

Request-idempotency records created after the backup cut may be lost too. Without them, the restored installation cannot recognize every repeated request or discover every external effect from that period.

Clients and operators must compare saved operation IDs and pending workflows with the known backup cut. Do not automatically restart a build, evaluation, and release sequence. Starting a new chargeable operation requires explicit authorization with the previous outcome's uncertainty visible.

The accepted data-loss window includes this limitation. **Disaster recovery cannot guarantee that each external operation runs exactly once.**

<a id="distinguish-disposable-trials-from-production-recovery"></a>

### Distinguish disposable trials from production recovery

Local trials use the same application and SeaweedFS topology. A trial user may explicitly choose disposable data and omit an off-host destination, provided the interface and documentation clearly state that **no production recovery target applies**.

A company production installation must configure the procedure, name its operator, and complete a restore rehearsal. A named Docker volume survives container replacement. It does not protect against losing its host disk.

Keep logs structured and remove sensitive values. Audit release, credential, permission, and deletion decisions in PostgreSQL. Show the latest completed backup cut and its age, failed transfers, last restore-test date, free disk space, worker and queue health, and dependency failures.

An operator-readable status view and a **runbook**, written operating instructions, are sufficient. V1 does not require a telemetry warehouse, CloudWatch, or a full tracing service.

<a id="restore-numerical-indexes-do-not-claim-to-reconstruct-them"></a>

<a id="restore-numerical-indexes-and-do-not-claim-to-reconstruct-them"></a>

### Restore numerical indexes and do not claim to reconstruct them

Manifests, hashes, and source bytes explain an index’s inputs and structure. They do not contain the numerical vectors themselves.

If Chroma is lost and no usable backup contains its required persistence, mark affected releases unavailable and report the loss. **Do not silently re-embed historical releases.** Re-embedding invokes the model again and produces another numerical execution rather than recovering the stored vectors.

Future index reconstruction needs its own design. It must account for cost, retention, deletion, and changes in model output over time. Newly generated numbers need distinct physical identities so they cannot overwrite retained results.

Creating a new PipelineVersion alone does not give those vectors distinct physical identities. The [saved batches used for vector retries](../../../.agents/skills/inframeld-indexing/references/profiles-and-preparation.md) are also insufficient. They protect unfinished writes and are not a permanent archive of every published vector.

Product-level reconstruction, its API/UI, and a general framework remain deferred alongside high availability and additional distributed recovery infrastructure.
