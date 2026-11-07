# Run the ordinary application worker

Use this guide to start, observe and stop the PostgreSQL-backed application worker. For example, after a worker process exits, a replacement uses the original job and its saved checkpoints rather than admitting replacement work.

The shared execution engine now registers `artifact.cleanup`, version `1`, for one original abandoned-staging target. Starting it does not enable document processing, builds or evaluations. There is no generic job submission, inspection, cancellation or continuation command, HTTP endpoint or SDK operation. The production composition and expired-attempt recovery are implemented. Targeted integration checks exercise original-invocation recovery and the registered PostgreSQL/S3 cleanup consumer. The focused private-preparation case has passed through real PostgreSQL, filesystem staging, S3 readback and conditional storage publication while retaining pending PUT evidence and remote charges. The producer case covers preparation. Separate maintained registered-worker/native and startup/queue tests cover worker continuation. The limits below bound execution. They do not establish measured capacity for the full installation or complete artifact cleanup.

## Prepare the database and configuration

Run commands from the repository root. Complete [local setup](../getting-started/local-setup.md), including locked backend dependencies and the explicit migration step. The worker and API must use compatible code and the same application database. This revision requires [0022_project_grant_results](../../../apps/backend/migrations/versions/0022_project_grant_results.py), whose parent is `0021_job_effect_observations`. [Migration 0021](../../../apps/backend/migrations/versions/0021_job_effect_observations.py) retains original storage-invocation admission and observations above `0020_project_membership`.

The existing operator-controlled migration command is:

```sh
mise exec -- pnpm --filter @inframeld/backend migrate
```

For an existing installation, follow the [upgrade procedure](upgrades.md#upgrades) before migrating. Worker startup checks the exact supported schema and reads the existing installation identity. It never migrates the database or generates a replacement identity. Missing or incompatible state prevents readiness. Installation-identity access uses `INFRAMELD_JOBS__DATABASE_TIMEOUT_SECONDS`. SIGINT or SIGTERM during startup cancels initialization and closes the pool without reporting readiness.

The worker requires database configuration, with `INFRAMELD_DATABASE__NAME`, `INFRAMELD_DATABASE__USER` and `INFRAMELD_DATABASE__PASSWORD` set. `HOST` defaults to `localhost` and `PORT` to `5432`. Use the host connection values from `apps/backend/.env` for the development database. The worker has no HTTP listener and requires no fingerprint key, incoming product credential or model-provider secret.

The worker also requires an operator-supplied private S3 endpoint, existing bucket and explicit storage credentials. Set `INFRAMELD_ARTIFACT_STORAGE__ENDPOINT_URL`, `INFRAMELD_ARTIFACT_STORAGE__BUCKET`, `INFRAMELD_ARTIFACT_STORAGE__ACCESS_KEY_ID` and `INFRAMELD_ARTIFACT_STORAGE__SECRET_ACCESS_KEY`. The endpoint must be reachable from the worker. Ambient AWS credentials are not used. `INFRAMELD_ARTIFACT_STORAGE__REGION` defaults to `us-east-1`.

For a private certificate authority, set `INFRAMELD_ARTIFACT_STORAGE__CA_BUNDLE` to an absolute, worker-readable CA file. Omit it to use system trust. Keep TLS verification enabled. The existing [storage settings](../../../apps/backend/src/inframeld_backend/shared/infrastructure/settings/artifact_storage_settings.py) own call bounds and the other optional settings. Configuring these values does not create storage, grant product authority or prove storage health.

Set `INFRAMELD_ARTIFACT_STAGING__ROOT` to the existing absolute staging directory owned by the worker's operating-system user, with mode `0700`. Internal preparation and cleanup must use the same root. Startup validates it and prepares private lock metadata without replacing a missing root. Keep the permanent per-attempt lock files. Staging and an arbitrary S3 endpoint do not establish a shared backing filesystem or measured capacity.

## Start on the host

With the database running and migrated, run:

```sh
mise exec -- uv run --project apps/backend --locked --env-file apps/backend/.env python -m inframeld_backend.application_worker
```

The `--env-file` option explicitly loads your ignored local configuration. The worker does not automatically load the API's dotenv files. The worker reads the required database, artifact-storage and staging settings, plus optional `INFRAMELD_JOBS__*`, `INFRAMELD_LOG_LEVEL` and `INFRAMELD_LOG_FORMAT` settings.

Look for `application_worker_ready` after schema and installation-identity checks pass. This confirms startup, not successful product work or continuing dependency health. Stop this foreground process with Ctrl-C when finished.

## Start with development Compose

As an alternative to the host process, use the opt-in `jobs` profile. Prepare the required artifact-storage variables in the environment running Compose. The host command's `--env-file` option does not prepare that separate environment. Compose forwards the endpoint, bucket, explicit credentials, region and optional CA path to the worker. It adds no storage service or CA mount. A private CA needs an operator-supplied container-readable path and mount. With the development dependencies running and the database already migrated, build the current image and start only the worker:

```sh
podman compose -f compose.dev.yaml --profile jobs up -d --build --no-deps application-worker
```

Use `docker compose` in place of `podman compose` on Docker. The service has no published port. It uses the development database on the Compose network, with a pool of two connections and no overflow. Host settings otherwise default to a pool of ten with up to twenty overflow connections. Keep the API and worker on compatible revisions when rebuilding.

The jobs profile binds `INFRAMELD_ARTIFACT_STAGING_HOST_ROOT`, defaulting to `/var/lib/inframeld/staging`, at the worker's `/var/lib/inframeld/staging`. Prepare that existing private host directory with the correct worker ownership before startup. Compose refuses to create a missing source path automatically. This mount does not measure or configure the S3 server's data filesystem.

Read recent worker events with:

```sh
podman compose -f compose.dev.yaml --profile jobs logs --tail 50 application-worker
```

Stop this service without stopping the database or other services:

```sh
podman compose -f compose.dev.yaml --profile jobs stop application-worker
```

## Configure bounded execution

These optional settings bound worker startup and execution. Values are seconds unless stated otherwise.

| Environment variable | Default | Allowed value |
| --- | --: | --- |
| `INFRAMELD_JOBS__LEASE_SECONDS` | 30 | Greater than zero, at most 120 |
| `INFRAMELD_JOBS__POLL_SECONDS` | 1 | Greater than zero, at most 30 |
| `INFRAMELD_JOBS__DATABASE_TIMEOUT_SECONDS` | 5 | Greater than zero, at most 5 |
| `INFRAMELD_JOBS__SHUTDOWN_SECONDS` | 15 | Greater than zero, at most 30 |
| `INFRAMELD_JOBS__WORK_SECONDS` | 7200 | Greater than zero, at most 7200 |

The lease must exceed twice the database timeout. A lease is a time-limited claim on a job. The worker renews it while an attempt runs. Only the current owner can save progress or completion, so a late result from an obsolete attempt cannot overwrite its replacement.

Logging accepts `INFRAMELD_LOG_LEVEL=DEBUG`, `INFO`, `WARNING` or `ERROR`, and `INFRAMELD_LOG_FORMAT=console` or `json`. Defaults are `INFO` and `console`. Keep configuration files private and remove credentials and private payloads from any diagnostic material you share.

Admission is a separate application responsibility. It atomically commits the job, original retry identity and required audit with the owning operation. The shared admission service defaults to eight queued plus running jobs and rejects new admissions when that finite capacity is full. The stored queue-wait deadline is 24 hours after admission. Equivalent admission retries keep the original job and operation identity through queued, running and terminal states. They do not admit another job or establish current progress. Admission limits belong to the owning application and are not worker settings. Restarting does not rewrite stored deadlines.

The worker claims the oldest eligible due job, using job ID to break ties. One ordinary attempt owns the execution slot. Checkpoints save completed units and check current authority and cancellation. They do not yield the slot to another job. One process-lifetime database pool supplies fresh sessions for preparation, invocation admission, observations and checkpoints, each bounded by `DATABASE_TIMEOUT_SECONDS`, at most five seconds. Preparation and admission sessions close before the S3 call. Storage waits do not retain those SQL transactions.

## Interpret events and recover safely

Queue reports use `application_worker_queue`, with `queue_depth`, `oldest_eligible_age_seconds` and `active`. Depth counts queued and running records. The age describes the oldest queued record whose retry time is due, or is `null` when none is due. `active` reports whether a running record exists. Reports occur at claim-loop boundaries, at least 30 seconds apart. An executing handler can delay the next report, so these events are not a periodic health guarantee.

| Observation | Meaning and next step |
| --- | --- |
| Exit code `2` with `{"code":"invalid_configuration"}` | Required configuration is missing or invalid. Check the named settings and bounds without printing secret values. |
| `application_worker_stopped` with `required_state_unavailable`, exit code `1` | Startup or runtime could not continue. Check database availability, schema compatibility, installation identity, and the configured original staging root/mount, worker ownership and private permissions. Restore the original root or mount before restarting, preserving permanent lock files and retirement metadata. |
| `application_worker_deferred` | A required queue or database observation could not be confirmed. The loop waits and tries again within its configured bounds. This does not establish that no earlier effect occurred. |
| `application_job_deferred` | The attempt needs bounded recovery. Preserve its identity and confirmed progress. The event alone does not establish whether external work happened. |
| `application_job_stopped` | The attempt stopped after an ownership, authority, cancellation or shutdown boundary. This is not proof of remote cancellation. |
| `application_job_failed` | A handler raised an error. Preserve the recorded evidence. An unknown external outcome can still require recovery. |
| `application_job_finished` | The current attempt saved successful completion. This says nothing about unrelated work. |

Stopping the process with SIGINT or SIGTERM stops new claims and gives active work up to `SHUTDOWN_SECONDS` to finish its bounded exit. Compose allows 20 seconds by default, longer than the worker's default 15-second grace. If you change that grace, keep the container stop allowance longer too. Shutdown preserves accepted work and checkpoints. It joins handler and lease tasks before closing the database pool, then drains and closes the storage client. The configured shutdown grace does not establish a separate storage-drain completion deadline. Forced process termination may interrupt that drain. Neither a stopped process nor a drained client proves that an earlier server-side write cannot finish. Shutdown may leave a running lease for the replacement to reconcile after expiry. It does not cancel a job, undo saved work or recall a sent provider request.

After an interrupted lease, safe remaining work can retry with retained checkpoints, bounded backoff and at most three attempts within the original work deadline. Restarting does not reset those budgets. Exhausted budgets or deadlines produce a recorded failure. An unsupported stored payload produces `failed` with reason `unsupported_payload` without running its handler. Do not edit stored payload bytes or queue rows to make a different release accept them.

If an external effect was started but its outcome is unknown, the job retains `recovery_required` and the engine does not automatically repeat that effect. Its original admission replay binding remains nonexpiring while the effect is unresolved. Keep the original operation identity and evidence. A restart, missing response or failed process is not permission to issue replacement paid work.

The registered cleanup consumer validates the current fence, original obligation, retained target and cleanup conditions. It retires the local producer before taking exclusive per-attempt ownership, rechecks stored facts, joins local work and durably removes the exact local target before releasing its local charge. Unrelated occupied bytes and remote charges remain. A matching saved remote acknowledgment suppresses DELETE redispatch only after validation and never skips unfinished local cleanup. A DELETE acknowledgment, an object-not-found observation or client drain does not establish remote physical retirement or release remote reservations. Without stored physical-completion facts, cleanup remains `recovery_required` with `physical_cleanup_pending`.

The claim path takes an unlocked candidate observation, then checks current Access authority for product work before acquiring the queue turn. It locks and matches that exact candidate before mandatory recovery of an expired attempt. Recovery checks current eligibility and the original effect binding. For a pending effect, matching unused `not_dispatched` proof is consumed with retirement of the old attempt in one transaction. Only eligible safe work is requeued with its original identity, deadlines, checkpoints and attempt budget. An unconfirmed pending effect retains `recovery_required`. An observation is not permission to dispatch, and no operator command can manufacture completion or release bytes.

Admitted work keeps its original principal and inputs. Ordinary credential expiry, replacement or individual key revocation does not cancel it. Protected boundaries recheck current account, exact permission and the saved human security generation. Lost authority stops further protected work, and restoring permission does not restart it. The shared admission contract accepts application evidence and generation-bound human OAuth evidence. Application-key authentication itself remains separate delivery work. Browser-derived durable admission is rejected until an owning caller implements qualified generation capture.

Identity-recovery cleanup runs through the separate [recovery worker](../getting-started/local-setup.md#private-recovery-callbacks), outside the ordinary attempt slot. It still shares the host and dependencies, so this separation does not promise a response time. Follow its own protected continuation procedure rather than applying ordinary-job retry rules to recovery.

The owning [jobs workflow](../../../.agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md) explains the accepted execution and uncertainty contracts. [Current-principal authority](../../../.agents/skills/inframeld-access-models/references/decision-admitted-work-authority.md#approved-resolution) explains credential changes after admission.
