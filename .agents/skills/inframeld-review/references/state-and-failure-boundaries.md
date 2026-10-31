# Review the state and failure boundary that changed

Alice uploads a handbook. Object storage accepts the bytes, but saving the admitted document fails. Her retry must follow the owning operation's identity and recovery rules. The review asks which partial state is permitted and what reconciles it. It does not assume that all stores share a transaction or that every abandoned object needs immediate deletion.

Read only sections whose trigger matches the changed behavior. These questions support Review's findings and existing ratings. Domain workflows own guarantees and allowed delays. Code, migrations and executed tests establish implementation. A theory or missing optional test is not itself a defect.

## Select the affected boundary

| Change touches | Questions to answer from the actual path | Useful evidence |
| --- | --- | --- |
| Persistent writes | What must save together, including required audit and operation outcome? What happens if validation, commit or response delivery fails? | Owning transaction and focused rollback or response-loss regression. |
| Concurrent writers or capacity admission | Can callers lose an update, claim the same work or exceed a limit? Which conditional write, constraint or lock preserves the invariant? | Actual persistence safeguard and a relevant concurrent integration case. A transaction alone does not prove sufficient isolation. |
| External effects or automatic retries | Could the remote action already have happened after a timeout? Which original identity and payload survive retry? How are known failure and uncertainty distinguished? | Dispatch/replay boundary, saved outcome and a lost-acknowledgment case. No repeated paid call merely to gather review evidence. |
| Background jobs | What progress survives crash or restart? Can an expired worker save after replacement? Which units are safe to repeat, and when are cancellation and current authority checked? | Claim, checkpoint and publication conditions, plus the affected restart, duplicate or stale-attempt test. |
| Derived data, caches or multiple stores | Which state is authoritative? What may lag? Can stale material bypass current authorization or readiness? How is partial publication or cleanup reconciled? | Authoritative binding, query/publication gate and the relevant failure window. Calling data derived does not prove reconstruction exists. |
| Schemas, durable payloads, upgrades or restore | Can the supported release interpret saved work? Is image rollback compatible with the schema? Can restore revive revoked access or erased content? | Affected migration, compatibility or recovery procedure and its actual qualification status. |
| Expensive work or queues | Which input and concurrency limits bound memory, disk and downstream work? What happens at saturation, including retained results and cleanup obligations? | Enforced bounds and representative measurements where they change the decision. Planning targets are not measured capacity. |

## Follow one useful failure

Start with the ordinary user outcome, then select the relevant point where execution can stop, repeat or overlap. Identify the required invariant, the implementing safeguard and what the available evidence proves. Use the existing finding format when there is a material gap. Do not add a separate ledger or fill every row as a mandatory form.

For Alice's failed admission, inspect the actual artifact identity, publication gate and existing cleanup obligation. A controlled test can show the decision and preserved error. Claims about database rollback or real storage compatibility need the corresponding integration evidence through maintained commands. If delayed orphan cleanup is accepted and remains bounded, its temporary existence is not automatically a finding.

If a worker finishes after its replacement, inspect the final persistence/publication condition, not only its initial lease check. If a caller loses a paid response, distinguish returning an existing receipt from dispatching again. These are different failure windows and may need different tests.

## Preserve the review boundary

A help-text correction does not activate database or restore analysis. A read-only status component can be reviewed against its accepted storage and authorization contract before a downstream workflow is implemented. Do not absorb that producer's implementation into the reader merely to demonstrate an unrelated end-to-end journey.

One server still permits concurrent callers and partial failures. It does not require consensus infrastructure, event sourcing, an outbox or a new workflow engine by default. Prefer the smallest existing mechanism preserving the required outcome. Reopen an accepted architecture choice only when evidence invalidates its assumptions, using the owning decision procedure.

Missing runtime evidence limits the affected claim. Do not invent a defect, claim full qualification from mocks or remove a required check to create a passing result. The [maintainability bar](scoring-and-report.md#apply-the-maintainability-bar) applies to the proposed remedy and its verification machinery too.

## Sources

[Transactions and partial failures](https://www.oreilly.com/library/view/designing-data-intensive-applications/9781098119058/ch08.html), [production failure and stability](https://pragprog.com/titles/mnee2/release-it-second-edition/) and [operational simplicity](https://sre.google/sre-book/simplicity/) motivate these questions. They are not additional standards or mandatory technology selections.
