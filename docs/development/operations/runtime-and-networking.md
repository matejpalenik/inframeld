# Operate the runtime and its network boundaries

<a id="operate-the-runtime-and-its-network-boundaries"></a>

The supported design is a single-server Docker Compose installation. The current development Compose stack is smaller than the full target. Use executable configuration for actual ports and service pins. Do not infer production delivery from an architecture diagram.

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
