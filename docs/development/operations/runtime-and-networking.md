# Operate the runtime and its network boundaries

<a id="operate-the-runtime-and-its-network-boundaries"></a>

The supported design is a single-server Docker Compose installation. The current development Compose stack is smaller than the full target. Use executable configuration for actual ports and service pins. Do not infer production delivery from an architecture diagram.

The opt-in `jobs` Compose profile runs the [ordinary application worker](application-jobs.md), with PostgreSQL-backed claims, checkpoints and bounded shutdown. Its production registry contains the artifact cleanup and Project deletion handlers. The `recovery` profile runs one separate recovery worker for routine identity recovery and suspension cleanup. Both families share one live local attempt, independent of ordinary job capacity. The worker has no listener and uses private Hydra administration plus private Kratos administration when suspension cleanup is enabled. Stop an older worker and confirm its exit before starting the first replacement with the shared claim guard. An earlier remote request can finish after its lease expires. [Local setup](../getting-started/local-setup.md#private-recovery-callbacks) owns the settings, and [protected maintenance](../getting-started/local-setup.md#inspect-or-continue-suspension-cleanup) owns the operator procedure. These processes do not establish delivery of the full product workload.

<a id="model-destination-allowlists"></a>

## Approve saved model destinations

The API process reads the deployment's exact model-destination lists through the backend settings. Both lists default to empty. Set their values as JSON arrays in the environment passed to the API, then start or recreate that process with the new configuration.

```dotenv
INFRAMELD_MODEL_CONNECTION_DESTINATIONS__HTTPS_BASE_URLS=["https://api.openai.com/v1","https://models.example.test/v1"]
INFRAMELD_MODEL_CONNECTION_DESTINATIONS__LOCAL_OLLAMA_BASE_URLS=["http://127.0.0.1:11434"]
```

The local Ollama exception applies to an explicitly approved, credential-free HTTP loopback IP URL in the backend's network namespace. A host service on 127.0.0.1 is not reached through a container's 127.0.0.1. Never expose provider administration or broaden networking to satisfy a save check.

The save-time policy checks the exact approved base URL, provider and authentication method without resolving or contacting the provider. Later calls need the separate [actual outbound destination enforcement](../../../.agents/skills/inframeld-application-contracts/references/model-dispatch-and-destinations.md#destinations). Save approval establishes no network reachability, credential or model-validation result.

<a id="operate-within-visible-limits"></a>

<a id="operations"></a>

<a id="5-operate-within-visible-limits"></a>

## Operate within visible limits

Operators need logs with secrets removed and a retention limit, plus visible job progress, errors, latency, disk use, and dependency health. Stop accepting work before storage or work budgets run out. Show how old the latest usable backup is, whether transfers failed, and the results of restore tests. V1 does not require an external monitoring platform.

[Observability](../../../.agents/skills/inframeld-pipelines/references/query-tracing-and-privacy.md) specifies separate operational and RAG-workload tracing switches, OTel/OpenInference/OTLP, project workload opt-out and configurable 30-day workload retention. The CLI exposes only authorized pipeline diagnostics. Operators configure platform tracing. Workload capture cannot depend on the initiating caller's inspection rights, and operational spans cannot bypass disabled workload capture by retaining its text.

Each release supplies Compose and configuration guidance, fixed images, matching API and worker versions, and the required parser/model assets. Check free space, secrets, TLS, identity, and storage before starting normal work. Never ship shared default credentials or an unauthenticated production mode.

Before changing stored state, follow the [maintenance sequence](upgrades.md#upgrades) and create a [coordinated backup](backups.md#backup). API and worker startup must not both try to migrate the database. A named volume survives replacing a container, but cannot survive losing the host disk. Keep a matching backup off-host, including identity state and required keys.

If published vectors are lost, restore them or seek operator intervention. Manifests explain how vectors were created but do not contain their numerical values. Temporary saved write batches are not a permanent vector archive.

<a id="find-the-exact-boundary"></a>

## Find the exact boundary

- [Runtime topology and storage](../../../.agents/skills/inframeld-architecture/references/runtime-deployment-and-storage.md) owns the accepted process, secret and exposure requirements.
- [Managed-local HTTP](../../../.agents/skills/inframeld-application-contracts/references/cli-local-runtime.md) is a narrow accepted CLI profile, not permission to publish remote HTTP or provider administration.
- [Local setup](../getting-started/local-setup.md) describes the smaller development stack.
- [Workload qualification](../../../.agents/skills/inframeld-architecture/references/supported-workload-and-qualification.md) separates calculations from measured capacity.

Use the inspected Compose files and settings for deployed values. Before making availability or recovery claims, follow PD-ARCHITECTURE-01 and PD-ARCHITECTURE-02. No high-availability topology is implied.
