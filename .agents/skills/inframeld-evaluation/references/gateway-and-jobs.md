# Integrate Ragas through the existing gateway and jobs

Alice starts generation and cancels while Ragas is still preparing its executor. Cancellation must reach those nested calls too. Checking only the final judge call would leave preparation free to spend money or send data outside Inframeld's normal controls.

## Roles and adapters

Generator and judge bindings explicitly select authorized saved connections and model settings. They may reuse a key through an existing connection, but do not modify Pipeline generation settings. Ragas supplies algorithms, not case management, authorization, durable scheduling or another workflow engine.

Infrastructure adapters explicitly inherit the selected Ragas interfaces and convert vendor types locally. Public application records remain Inframeld-owned. Domain/application contracts must not import vendor schemas, SDK clients or credentials. Inspected v0.4.3 interfaces establish source compatibility only, not an executed integration.

## Follow all paid work

1. Admit bounded work through existing durable jobs and current operation authority. Observe every relevant connection-access revision.
2. Route extraction, synthesis, preparation, final judging, repairs and optional future embeddings through ModelGateway. No default provider clients, implicit model fallback or independent credentials are allowed.
3. Apply gateway limits and retry decisions to nested calls. Cancellation covers preparation before a library executor is returned.
4. Preserve checkpoints and partial results. A lost response or cancellation request is not proof that a dispatched call stopped or incurred no charge.
5. Stop later dispatch after relevant access changes and perform final consistency checks. Recovery follows the existing attempt/uncertainty protocol rather than unbounded regeneration.

Disable Ragas analytics and exporters and verify network behavior. This does not disable independently controlled Inframeld tracing. Additional judging/generation presets and external exporters remain deferred.

## Failure and qualification

No reference answer or expected evidence enters Pipeline execution. All protected egress and later disclosure retain current access checks. Budget, cancellation, uncertain paid outcomes and library preparation need behavioral qualification, not merely signature-compatible adapters.

The guide owns routing, limits, failure, network and human-calibration qualification plans. No new MCP tools, runner, public schema or SDK-distribution choice follows from adopting Ragas.

- [Gateway adapters and pinned source evidence](../../../../docs/development/evaluation.md#gateway), [Evaluation qualification](../../../../docs/development/evaluation.md#qualification), [Model connections](../../../../docs/development/model-connections.md), [Jobs](../../../../docs/development/jobs-and-idempotency.md) and [maintainer checks](../../../../docs/development/evaluation.md#maintainer-checks).
- [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) and [CLI delivery](../../../../docs/development/cli-delivery-plan.md) preserve application ownership and remaining qualification.
