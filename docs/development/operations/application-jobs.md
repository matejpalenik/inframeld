# Run the ordinary application worker

Use this guide to start, observe and stop the PostgreSQL-backed application worker. For example, after a worker process exits, a replacement uses the original job and its saved checkpoints rather than admitting replacement work.

The shared execution engine is implemented. Its default production handler registry is empty, so starting this process does not enable document processing, builds or evaluations. There is no generic job submission, inspection, cancellation or continuation command, HTTP endpoint or SDK operation. Qualification uses private local handlers, which are not operator features. The limits below bound the engine. They do not establish measured capacity for the full installation.

## Prepare the database and configuration

Run commands from the repository root. Complete [local setup](../getting-started/local-setup.md), including locked backend dependencies and the explicit migration step. The worker and API must use compatible code and the same application database at schema `0010_durable_jobs`.

The existing operator-controlled migration command is:

```sh
mise exec -- pnpm --filter @inframeld/backend migrate
```

For an existing installation, follow the [upgrade procedure](upgrades.md#upgrades) before migrating. Worker startup checks the exact supported schema and reads the existing installation identity. It never migrates the database or generates a replacement identity. Missing or incompatible state prevents readiness.

The worker requires database configuration, with `INFRAMELD_DATABASE__NAME`, `INFRAMELD_DATABASE__USER` and `INFRAMELD_DATABASE__PASSWORD` set. `HOST` defaults to `localhost` and `PORT` to `5432`. Use the host connection values from `apps/backend/.env` for the development database. The worker has no HTTP listener and requires no fingerprint key, incoming product credential or model-provider secret.

## Start on the host

With the database running and migrated, run:

```sh
mise exec -- uv run --project apps/backend --locked --env-file apps/backend/.env python -m inframeld_backend.application_worker
```

The `--env-file` option explicitly loads your ignored local configuration. The worker does not automatically load the API's dotenv files. The worker reads the database settings and optional `INFRAMELD_JOBS__*`, `INFRAMELD_LOG_LEVEL` and `INFRAMELD_LOG_FORMAT` settings.

Look for `application_worker_ready` after schema and installation-identity checks pass. This confirms startup, not successful product work or continuing dependency health. Stop this foreground process with Ctrl-C when finished.

## Start with development Compose

As an alternative to the host process, use the opt-in `jobs` profile. With the development dependencies running and the database already migrated, build the current image and start only the worker:

```sh
podman compose -f compose.dev.yaml --profile jobs up -d --build --no-deps application-worker
```

Use `docker compose` in place of `podman compose` on Docker. The service has no published port. It uses the development database on the Compose network, with a pool of two connections and no overflow. Host settings otherwise default to a pool of ten with up to twenty overflow connections. Keep the API and worker on compatible revisions when rebuilding.

Read recent worker events with:

```sh
podman compose -f compose.dev.yaml --profile jobs logs --tail 50 application-worker
```

Stop this service without stopping the database or other services:

```sh
podman compose -f compose.dev.yaml --profile jobs stop application-worker
```

## Configure bounded execution

These optional settings affect the worker loop. Values are seconds unless stated otherwise.

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

The worker claims the oldest eligible due job, using job ID to break ties. One ordinary attempt owns the execution slot. Checkpoints save completed units and check current authority and cancellation. They do not yield the slot to another job. Provider waits occur outside SQL transactions.

## Interpret events and recover safely

Queue reports use `application_worker_queue`, with `queue_depth`, `oldest_eligible_age_seconds` and `active`. Depth counts queued and running records. The age describes the oldest queued record whose retry time is due, or is `null` when none is due. `active` reports whether a running record exists. Reports occur at claim-loop boundaries, at least 30 seconds apart. An executing handler can delay the next report, so these events are not a periodic health guarantee.

| Observation | Meaning and next step |
| --- | --- |
| Exit code `2` with `{"code":"invalid_configuration"}` | Required configuration is missing or invalid. Check the named settings and bounds without printing secret values. |
| `application_worker_stopped` with `required_state_unavailable`, exit code `1` | Startup or runtime could not continue. Check database availability, schema compatibility and installation identity. Repair the cause before restarting. |
| `application_worker_deferred` | A required queue or database observation could not be confirmed. The loop waits and tries again within its configured bounds. This does not establish that no earlier effect occurred. |
| `application_job_deferred` | The attempt needs bounded recovery. Preserve its identity and confirmed progress. The event alone does not establish whether external work happened. |
| `application_job_stopped` | The attempt stopped after an ownership, authority, cancellation or shutdown boundary. This is not proof of remote cancellation. |
| `application_job_failed` | A handler raised an error. Preserve the recorded evidence. An unknown external outcome can still require recovery. |
| `application_job_finished` | The current attempt saved successful completion. This says nothing about unrelated work. |

Stopping the process with SIGINT or SIGTERM stops new claims and gives active work up to `SHUTDOWN_SECONDS` to finish its bounded exit. Compose allows 20 seconds by default, longer than the worker's default 15-second grace. If you change that grace, keep the container stop allowance longer too. Shutdown preserves accepted work and checkpoints. It may leave a running lease for the replacement to reconcile after expiry. It does not cancel a job, undo saved work or recall a sent provider request.

After an interrupted lease, safe remaining work can retry with retained checkpoints, bounded backoff and at most three attempts within the original work deadline. Restarting does not reset those budgets. Exhausted budgets or deadlines produce a recorded failure. An unsupported stored payload produces `failed` with reason `unsupported_payload` without running its handler. Do not edit stored payload bytes or queue rows to make a different release accept them.

If an external effect was started but its outcome is unknown, the job retains `recovery_required` and the engine does not automatically repeat that effect. Keep the original operation identity and evidence. A restart, missing response or failed process is not permission to issue replacement paid work.

Admitted work keeps its original principal and inputs. Ordinary credential expiry, replacement or individual key revocation does not cancel it. Protected boundaries recheck current account, exact permission and the saved human security generation. Lost authority stops further protected work, and restoring permission does not restart it. This foundation accepts application-key evidence and generation-bound human OAuth evidence. Browser-derived durable admission is rejected until an owning caller implements qualified generation capture.

Identity-recovery cleanup runs through the separate [recovery worker](../getting-started/local-setup.md#private-recovery-callbacks), outside the ordinary attempt slot. It still shares the host and dependencies, so this separation does not promise a response time. Follow its own protected continuation procedure rather than applying ordinary-job retry rules to recovery.

The owning [jobs workflow](../../../.agents/skills/inframeld-application-contracts/references/jobs-and-recovery.md) explains the accepted execution and uncertainty contracts. [Current-principal authority](../../../.agents/skills/inframeld-access-models/references/decision-admitted-work-authority.md#approved-resolution) explains credential changes after admission.
