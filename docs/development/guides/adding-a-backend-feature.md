# Add one backend behavior

<a id="add-one-backend-behavior"></a>

Suppose Alice needs to give Bob use-only permission on Support. The existing grant operation is a useful example because it includes a domain rule, current authority, a retry and a database write. The short load → act → save loop is only the domain-change part of the operation.

<a id="find-the-owner-and-decision-boundary"></a>

## Find the owner and decision boundary

Read [Coding Standards](../../../.agents/skills/inframeld-coding-standards/SKILL.md) before suggesting or writing code, including tests. Load the [Access blueprint](../../../.agents/skills/inframeld-access-models/references/architecture.md) and the relevant workflow. Read pending decisions only when their trigger affects the new component. An ordinary implemented grant change does not need to settle unrelated key or production-recovery questions.

Repository writes require the exact confirmation described in [AGENTS.md](../../../AGENTS.md). A design discussion or loaded skill grants no write permission.

<a id="follow-the-components-through-the-request"></a>

## Follow the components through the request

1. Choose domain, layer and role using [component roles](../../../.agents/skills/inframeld-coding-standards/references/component-roles-and-imports.md). Access owns grants. HTTP is an adapter, not another permission engine.
2. Convert boundary input into a Command and distinct values. Follow [static mappers](../../../.agents/skills/inframeld-coding-standards/references/static-utilities-and-mappers.md) and [typed values](../../../.agents/skills/inframeld-coding-standards/references/values-and-records.md). Keep authenticated access, requested change and retry context separate.
3. Follow the complete [service example](../../../.agents/skills/inframeld-coding-standards/references/services-and-use-cases.md). It injects capabilities, computes the fingerprint, owns the transaction, checks current authority and returned scope, then handles replay before loading membership.
4. Give the aggregate its business transition and use its specific repository. [Aggregates and repositories](../../../.agents/skills/inframeld-coding-standards/references/aggregates-and-repositories.md) explains scoped loading, unchanged saves and transaction-bound snapshots. Do not modify a private collection from the service.
5. Keep typed protocol and adapter conversion at the boundary. Read [protocols and persistence](../../../.agents/skills/inframeld-coding-standards/references/protocols-and-persistence.md). Bootstrap constructs concrete collaborators and closes resources.
6. Write a behavioral test through the scaffold-first sequence in [testing conventions](../../../.agents/skills/inframeld-coding-standards/references/testing-and-documentation.md). Require the intended failure before implementing behavior. Then follow [test procedures](testing.md).
7. Declare the actual HTTP contract in code and run the [contract checks](contracts-and-data.md). Required audit and completion must commit with the change. Return success only after transaction exit succeeds.

<a id="choose-the-appropriate-variation"></a>

## Choose the appropriate variation

A read uses a typed projection when no business transition is needed. Creating a new aggregate differs from loading an existing membership. Provider calls keep their documented external-I/O boundaries, rather than copying a database-only transaction around a network wait. These are ordinary variations, not permission to omit authorization or retry safeguards.

Update the owning reference when behavior changes. Record a new architectural choice through the [just-in-time process](architecture-decisions.md#just-in-time-architecture-decisions), with explicit approval before dependent implementation.
