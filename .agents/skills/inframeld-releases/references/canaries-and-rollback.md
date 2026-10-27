# Try a candidate, promote it or roll back

<a id="try-a-candidate-promote-it-or-roll-back"></a>

Production serves A, retains Z as previous and has ready candidate B. Alice wants to try B with a small audience before promotion. Candidate rejection and rollback have different pointer effects and must not be treated as interchangeable undo commands.

<a id="cohorts-are-routing-not-identity"></a>

## Cohorts are routing, not identity

Authenticate and authorize first. Stable principal and rollout identities participate in the canary bucket. The affinity key is routing input, not permission or verified end-user delegation.

A shared application account remains one principal. Rotating its key or increasing the percentage must not reshuffle existing callers. Ten percent describes a share of identities, not an exact request count.

Use the guide's deterministic assignment contract rather than inventing another hash or per-request random choice. Preserve bounded candidate identity, selected version and receipt attribution. A 0% candidate is still attached and blocks switching to Automatic.

<a id="follow-each-transition"></a>

## Follow each transition

| Operation | Result |
| --- | --- |
| Attach or adjust B | A remains current. B receives only the selected stable cohort. |
| Reject or abort B | A remains current and Z remains previous. B is detached. |
| Promote B | B becomes current and A becomes designated previous. |
| Roll back after promotion | Use the eligible designated previous target under the one-step contract. Consume that target. |

Canaries and rollback require Manual mode. A candidate blocks rollback under the selected contract.

Missing, erased or unhealthy targets cannot be replaced silently by another historical version. Report unavailable rollback without changing current.

Configuration restoration merely creates new working configuration history and is not a production rollback.

<a id="failures-and-concurrent-commands"></a>

## Failures and concurrent commands

Every transition checks current target-specific release authority, readiness, usable dependencies and expected serving/control state. A stale command conflicts instead of overwriting another operator's decision. Failure preserves healthy current. Current permissions and source erasure apply even to retained versions.

Pipeline rollback does not restore shared model access settings or old credentials. A successful score or positive feedback may inform Alice but cannot authorize a transition or switch Automatic off by itself.

<a id="release-a-candidate-deliberately"></a>

<a id="manual"></a>

<a id="5-release-a-candidate-deliberately"></a>

## Release a candidate deliberately

Initial creation requires one genuinely ready, same-project, contract-compatible PipelineVersion and an authorized initial decision.

Create Deployment authorizes a human to create a new Deployment with that initial version. Save its explicit creator permissions, including can-use-and-grant Manage releases, in the creation transaction. Later releases need current Manage releases on that exact Deployment. Build and access to protected inputs remain separate, and creation grants nothing on other Deployments. [Access](../../inframeld-access-models/references/memberships-groups-and-handover.md#section-bound-administration-grants-and-recovery) and [first publication](../../inframeld-architecture/references/first-use-and-private-defaults.md) define these checks.

Save the initial Deployment revision with that version as current. It has no candidate, previous version, or rollout, so there is no baseline cohort or rollback target yet.

The first endpoint needs a genuinely ready version, but no fictional version, judge setup, or benchmark. A benchmark is a set of evaluation cases. Evaluation is not required before this first creation.

<a id="keep-canary-assignment-stable-with-an-affinity-key"></a>

### Keep canary assignment stable with an affinity key

A **cohort** is a group of routing identities assigned to a variant. A **variant** is the version a request actually uses: current or candidate during a canary.

An **affinity key** identifies the application’s user or session for routing. It does not authenticate that person or grant document access.

<a id="authenticate-first-then-determine-routing-affinity"></a>

### Authenticate first, then determine routing affinity

| Caller | Affinity input |
| --- | --- |
| **Human querying through CLI or future Studio** | The stable internal human principal ID. A principal is the identity Inframeld recognizes as the caller. |
| **Customer application** | A bounded opaque `affinityKey` supplied for its end user or session, scoped to the authenticated integration principal. |

Authenticate the caller and check Query permission before selecting a routing group. [Access](../../inframeld-access-models/references/authorization.md) defines human sessions and application keys.

Keep application affinity values opaque, without emails or unnecessary personal data. They route requests and prove neither identity nor permission.

<a id="calculate-one-deterministic-bucket"></a>

### Calculate one deterministic bucket

For application requests, the routing inputs are:

```text
organization ID
    + project ID
    + deployment ID
    + stable integration-principal ID
    + affinityKey
    + rollout ID
```

For human requests, use the stable internal human ID as the affinity input.

A fixed, versioned cryptographic hash or keyed hash (HMAC) assigns a bucket from 0 to 9,999. Save which routing algorithm was used. A language runtime's randomized hash would not keep assignments stable.

The selection rule is:

```text
candidate, when bucket < canary percentage × 100
current, otherwise
```

**The percentage is not an input to the hash.** Changing the allocation moves the threshold, not the identities’ buckets.

<a id="example-increase-the-allocation-without-reshuffling-existing-buckets"></a>

### Example: increase the allocation without reshuffling existing buckets

| Affinity identity | Fixed bucket | At 10%: threshold 1,000 | At 25%: threshold 2,500 |
| --- | --: | --- | --- |
| Alice | 630 | Candidate | Candidate |
| Bob | 1,850 | Current | Candidate |

Increasing the percentage includes more buckets while Alice remains in the candidate cohort.

Setting the same rollout to 0% pauses candidate traffic but preserves its buckets for a later increase. Replacing the candidate creates a new rollout ID and deliberately starts a new assignment.

<a id="keep-integration-identity-stable-across-credential-rotation"></a>

### Keep integration identity stable across credential rotation

Replacing SupportBot's key must not move its users between versions. Hash its stable principal ID, not the credential. A newly created application has a different routing scope.

With candidate traffic enabled, an application request missing affinity returns `422 affinity_required`. Do not use its credential to place all users in one bucket or choose randomly per request. Affinity is optional when there is no candidate traffic.

A 10% canary means 10% of affinity identities, not necessarily 10% of requests. One busy user can generate most traffic. Show actual requests and failures per version, and avoid significance claims based on tiny groups.

<a id="apply-the-same-safety-checks-to-every-release-transition"></a>

### Apply the same safety checks to every release transition

Every transition requires permission, an **idempotency key**, and **`expectedRevision`**.

The request key identifies a retry. The expected Deployment revision identifies the state Alice reviewed, preventing her command from overwriting Bob's later decision.

Check the caller's project and resource scope, validate the transition, and save state plus audit only if the expected revision still matches. Recheck the target's availability during the change instead of trusting an earlier screen.

<a id="manual-release-commands"></a>

### Manual-release commands

All five commands below require **Manual releases**. In Automatic updates, return a typed mode conflict instead of silently changing modes.

| Command | Effect |
| --- | --- |
| **Attach candidate B** | Keep current A. Set candidate B, create a new rollout identity, and start at **0%**. Reject an existing candidate unless it has first been explicitly aborted. |
| **Set canary percentage** | Change the candidate allocation only. Current/candidate version identities and the rollout’s bucket assignments remain fixed. |
| **Abort candidate** | Keep current and previous unchanged. Clear the candidate and its active rollout traffic. Retain build and evaluation evidence. |
| **Promote** | Set previous to current A, then current to candidate B. Clear the candidate and candidate traffic. Preserve evidence. |
| **Roll back promotion** | Restore previous A as current and clear `previous`, consuming that one-step rollback target. Retain B’s immutable evidence. |

These operations change release state, not the immutable versions or their evidence.

A candidate cannot equal current. Explicitly abort an attached candidate before replacing it, even when its traffic is 0%.

Changing allocation never promotes the candidate by itself. Promotion remains a separate command even at 100% candidate traffic.

<a id="rollback-is-neither-candidate-rejection-nor-an-unlimited-history-browser"></a>

### Rollback is neither candidate rejection nor an unlimited history browser

An attached candidate blocks rollback with `409 candidate_active`. Abort it first so a rollback cannot unexpectedly both reject a trial and undo an earlier release.

Keep only one immediate rollback target, including after automatic publication. Releasing an older historical version needs an explicit new candidate and release, rather than walking an unlimited rollback stack.

Rollback requires manual mode and leaves it selected. Re-enabling automatic updates is a new decision to apply the selected inputs. Successful rollback never enables it implicitly.

<a id="reject-a-bad-canary-without-undoing-the-current-release"></a>

### Reject a bad canary without undoing the current release

Start with previous Z, current A, and candidate B. B produces errors, so the engineer invokes `abort_candidate`.

```text
Before: previous Z | current A | candidate B
After:  previous Z | current A | no candidate
```

A remains current. Restoring Z would incorrectly undo A, which was not the release being tested.

<a id="undo-a-completed-promotion"></a>

### Undo a completed promotion

Start with current A and candidate B. Promote B, then later roll it back:

```text
Before promotion: current A | candidate B
After promotion:  current B | previous A | no candidate
After rollback:   current A | no previous | no candidate
```

Rollback clears previous rather than storing B there for automatic back-and-forth switching. B's immutable evidence remains available for inspection, and an authorized person can later attach B as a new candidate.

<a id="report-an-unavailable-rollback-target-without-changing-current"></a>

### Report an unavailable rollback target without changing current

Current is B and previous is A, but A’s required materialization is unavailable or its source was explicitly erased.

Return **`409 rollback_target_unavailable`** with safe same-project details. B remains current. Do not substitute another version or search an unfiltered corpus.

An operator may restore the missing dependency or release a different valid candidate.

<a id="reject-a-stale-command-from-a-concurrent-operator"></a>

### Reject a stale command from a concurrent operator

Two operators both read Deployment revision **8**. One promotes B and commits revision **9**. The other’s command still expects revision 8 and receives **`409 stale_revision`**.

Reload and ask the operator to decide from the new state. The client cannot quietly replace revision 8 with 9 and repeat the old promotion.

<a id="status-and-sources"></a>

## Status and sources

These are accepted pointer/cohort rules, not evidence of a delivered canary engine or qualified load distribution. Explain A/Z/B outcomes separately and inspect implementation before claiming a transition exists.

- [Canary and rollback behavior](../../inframeld-pipelines/references/configuration-queries-and-builds.md), [Release records](records-and-transitions.md#releases), [Access](../../inframeld-access-models/references/authorization.md), [feedback attribution](../../inframeld-pipelines/references/answer-feedback.md) and [maintainer checks](../../inframeld-pipelines/references/configuration-queries-and-builds.md#maintainer-checks).
- [ADR-0032](../../../../docs/adr/ADR-0032-keep-canary-assignment-stable-for-the-same-caller-and-affinity-key.md) owns stable affinity. [ADR-0047](../../../../docs/adr/ADR-0047-support-reversible-publication-modes-per-deployment.md) owns mode boundaries. [ADR-0008](../../../../docs/adr/ADR-0008-preserve-immutable-versions-and-their-provenance.md) explains immutable lineage.
