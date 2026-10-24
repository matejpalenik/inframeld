# Vector writes and frozen-payload retries

One shard accepts Alice's new vectors while another times out. The materialization is still unready. Recovery must establish which exact records exist without inventing another numerical execution or repeating a paid model call whose outcome is unknown.

## Capture before dispatch

The singleton vector writer stays in the existing worker and holds a process-lifetime local lock. API handlers never mutate Chroma.

SQL attempt/revision checks decide whether a result may publish. They do not cancel already dispatched storage or provider work.

1. Admit the intended generation and save exact bounded vector IDs and payload bytes before vector dispatch.
2. Record dispatch under the accepted attempt protocol, then insert through the single writer.
3. After a storage timeout or partial result, retry only the same saved IDs and bytes. Do not recompute embeddings or generate fresh IDs for this retry.
4. Read actual records back and verify their identities and contents against the frozen expectation. A global shard count cannot prove exact materialization contents.
5. Publish readiness conditionally only after complete verification and current attempt/retention guards. Partial success remains unready.

The retry spool is bounded temporary infrastructure, not a permanent vector backup. Deterministic saved layout and expected records make verification possible. A semantic reuse key cannot prove that an uncertain numerical execution returned identical vectors.

## Separate model uncertainty from storage uncertainty

A storage retry can reuse already captured bytes. A provider timeout before bytes were captured cannot.

After a provider timeout, it is unknown whether the model processed or billed the embedding request. That timeout does not authorize another paid embedding call. Use the existing durable job uncertainty/recovery contract rather than a hidden retry loop.

A stale worker may still finish remote work after losing authority. Fencing prevents it publishing readiness. It does not undo those side effects. Tombstones and retention protect against late writes to retired identities, using their separate cleanup protocol.

## Failure scope and qualification

An uncertain candidate generation does not automatically make an independent healthy serving generation unavailable. Ordinary frozen-payload retries do not require routine Chroma restarts.

Corruption and unresolved cleanup may need intervention. Reconsider a failed backend assumption rather than introducing another engine, distributed coordinator or unbounded work splitting.

These are accepted protocols. Use the guide's backend-contract, failure and resource tests without claiming they ran. Inspect worker/storage adapters before describing a protocol as implemented.

- [Frozen vector retries](../../../../docs/development/indexing.md#retries), [Indexing qualification](../../../../docs/development/indexing.md), [jobs and idempotency](../../../../docs/development/jobs-and-idempotency.md) and [retirement](../../../../docs/development/indexing.md#retirement).
- [ADR-0011](../../../../docs/adr/ADR-0011-retry-frozen-vector-identities-and-payloads.md) explains why retries freeze both identity and payload. [ADR-0010](../../../../docs/adr/ADR-0010-save-deterministic-layouts-for-vector-shards.md) explains saved layouts.
