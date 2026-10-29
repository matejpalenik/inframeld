# Supported workload and qualification

<a id="supported-workload-and-qualification"></a>

Alice needs to know whether an installation can handle her corpus while serving questions. The calculations below define experiments and their assumptions. They are not measured capacity or production guarantees.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="measure-the-supported-workload"></a>

<a id="qualification"></a>

<a id="6-measure-the-supported-workload"></a>

## Selected initial qualification gate

Accepted [PD-ARCHITECTURE-01](decision-supported-operating-envelope.md#approved-resolution) selects the first profile: 200 current documents, 2,000 current chunks, 10,000 physical vectors, one active answer execution, and the specified shared queue/storage/filter/deadline bounds on the 16-vCPU/64-GiB/1-TB host. Apply those bounds and its one-query mixed-load objectives for initial release qualification. They are selected targets, not measured support.

The larger 25,000-document/500,000-vector, five-query and million-document material below is retained as an explicitly separate expansion experiment and cost explanation. It is not the initial go/no-go gate. Passing it does not silently enlarge the accepted profile.

## Measure the supported workload

These estimates do not establish production capacity. Test the exact single-node Chroma image digest and matching SDK that the release will ship. Do not use floating `latest` versions, apply cloud quotas to the local server, or rely on cloud-only forks or experimental search features.

The design uses explicit embeddings and metadata generation filters. It does not depend on Chroma conditional transactions. Large `$in` filters, canonical float32 read-back, late writes, and cleanup barriers require tests against the pinned server. Historical vendor observations are not current qualification evidence.

<a id="a-million-documents-is-not-the-qualified-capacity"></a>

### A million documents is not the qualified capacity

One million documents averaging 20 chunks produce 20 million vectors. At 1,536 float32 dimensions, their coordinates alone occupy **122.88 GB decimal, approximately 114.4 GiB, per profile**. Metadata, index overhead, and the other services require additional space and memory.

The proposed 64 GiB test host below is not a promise to support a million documents. More hardware may help, but constructing authorized generation lists and sending large filters can still require a different adapter strategy. Shards and application interfaces protect domain boundaries without making that future migration easy.

<a id="provisional-qualification-environment-and-workload"></a>

### Provisional qualification environment and workload

**Everything in this section is a planning assumption, not measured capacity, a supported limit, or a service-level agreement.**

Use one Linux server with **16 vCPUs, 64 GiB RAM, and 1 TB usable local SSD/NVMe storage**, plus off-host backups. Run one Chroma server with two fixed shards. Model inference runs remotely or through the customer's gateway. Local language-model memory is excluded.

<a id="proposed-memory-allocation"></a>

### Proposed memory allocation

| Component                             | Planning budget |
| ------------------------------------- | --------------- |
| Chroma                                | 32 GiB          |
| PostgreSQL                            | 6 GiB           |
| Parser, one attempt                   | 8 GiB           |
| SeaweedFS                             | 4 GiB           |
| API, worker, console, and ingress     | 4 GiB           |
| Kratos                                | 1 GiB           |
| Operating system, cache, and headroom | 9 GiB           |
| **Total**                             | **64 GiB**      |

<a id="proposed-workload"></a>

### Larger expansion workload

| Dimension | Initial target and stress variants |
| --- | --- |
| **Corpus** | 25,000 current documents averaging 20 chunks: 500,000 current vectors. Test stages at 1,000, 10,000, then 25,000 documents. Run a deliberate 50,000-document stress experiment. |
| **Sources and text** | Average source size 0.5 MiB. Average chunk text 2 KiB. Test unusually large inputs with explicit per-source limits. |
| **Profiles** | One active 1,536-dimensional float32 profile. A second profile is a separate stress experiment. |
| **Retention and change** | Three retained collection revisions. Daily changes to 1% of documents at stable document count. Additional pins/builds consume admission budget. |
| **Permissions** | 20 groups. A typical user belongs to two. Test permitted fractions of 100%, 50%, 1%, and 0%, including permission changes during queries. |
| **Filters and metadata** | Measure against a metadata target of at most 1 KiB per record. A list of 25,000 UUID-style generation IDs is roughly 1 MB of JSON per shard, not a verified backend allowance. |
| **Work** | Initial ingestion target of one document per second. One build and one evaluation at a time, sharing resource limits with serving. |
| **Queries** | Five concurrent end-to-end requests. Also test concurrency of 1 and 10, plus controlled arrival rates that expose queueing. |

<a id="storage-and-time-calculations-are-not-total-resource-predictions"></a>

### Storage and time calculations are not total-resource predictions

With equal-sized, distinct 1% changes between three retained revisions, their union is approximately **510,000 vectors**, not three complete copies. Their coordinates occupy **3.13344 GB decimal / approximately 2.92 GiB**. Three full physical snapshots would require approximately **9.216 GB** of coordinates.

Extra profiles, larger changed documents, retained pins, and failed-attempt cleanup increase storage. At the assumed source size, current sources occupy about **12.2 GiB before old versions**. One copy of 510,000 chunks at 2 KiB is about **1 GiB**.

Parsed artifacts, PostgreSQL's write-ahead log (WAL), indexes, duplicate text, retry spool, scratch space, and backups are additional. These calculations do not predict total consumption.

At one document per second, 25,000 documents take at least approximately **6.9 hours**, before slower phases or queues. A 1% change adds about **250 documents / 5,000 chunks** to process, but full manifest/verification reads and query authorization still involve the larger corpus.

<a id="qualification-tests-and-stopping-rules"></a>

### Qualification tests and stopping rules

Run these tests against pinned images and a recorded host, corpus, and workload. They are requirements before making production claims, **not tests completed by writing this section**.

<a id="backend-contract"></a>

### Backend contract

Prove duplicate `add` behavior, partial completion, read visibility, restart durability, and float32 read-back verification with explicit embeddings.

Drop responses before and after the backend applies a request. Replay frozen batches in different orders and terminate workers between every durable step.

Pass only if published bytes never change, partial materializations never become available for serving, and healthy old releases continue without routine Chroma restarts.

**If the assumed backend contract fails, stop and reconsider the adapter/protocol. Do not hide the failure inside a larger retry loop.**

<a id="end-to-end-lifecycle"></a>

### End-to-end lifecycle

Ingest, verify, publish, and back up R1. While serving queries, change one document at corpus sizes of 1,000, 10,000, and 25,000, then test random and localized 1% changes.

Build, verify, and evaluate R2. Try canary traffic, promotion, and rollback. After R1's pins end, retire it and measure cleanup, including compaction, the storage work that reclaims deleted space.

Count all PostgreSQL, artifact-store, and Chroma reads and writes. **Membership-only changes must issue zero writes to surviving vector records.** Record the full verification and snapshot costs that remain.

<a id="security-and-failures"></a>

### Security and failures

Test forged scope/group input, zero permitted generations, revocation during queries, failed shards, stale SQL publication, query-pin-versus-GC races, and delayed insertion after deletion.

Pass only if every content send or response follows its final scope check, a failed shard produces an explicit failure, and retired generations never become live again. Keep evidence of pending cleanup until the tested completion procedure proves it finished.

Test revocation before the send check, just after it, and before the response check. The first blocks the send. The second has the already-approved-send limitation described above. The third suppresses the response. A successful retry must never be treated as proof of physical erasure.

<a id="resources-and-performance"></a>

### Resources and performance

Record phase duration, resident-memory and container-memory peaks, CPU use, disk/WAL/spool growth, queue age, provider usage, serialized filter size, and PostgreSQL authorization work.

Measure filtered approximate-nearest-neighbor latency at **p50, p95, and p99** and **recall@k** against an exact, correctly scoped reference on a representative fixture. Percentiles describe the latency distribution. Recall@k measures how many of the exact reference's top-k neighbors the approximate search recovers.

Report model/judge time separately. Include warm and cold queries and a build running under query load.

Resource budgets must reject admission visibly **before** out-of-memory failure, sustained swapping, or an unbounded backlog.

<a id="provisional-gono-go-goals"></a>

### Larger expansion go/no-go experiments

| Measurement | Proposed goal |
| --- | --- |
| **Database retrieval, including authorization and filter construction** | p95 at most 1 second at five concurrent requests during a small build, as an expansion experiment. |
| **Retrieval quality** | recall@10 of at least 0.95 on the declared fixture. |
| **One-document release platform overhead** | At most 2 minutes. |
| **1% change platform overhead** | At most 15 minutes. |

Report parser/model time and complete end-to-end time separately. These goals remain proposals for qualification, not accepted capacity claims.

If the 25,000-generation filter or its payload limit fails, or measured latency misses the goal, lower the qualified workload or reconsider the adapter before advertising support. Do not silently remove scope predicates, expand bounds indefinitely, or add segment/compaction infrastructure merely to preserve an unproven target.

<a id="end-to-end-product-qualification"></a>

### End-to-end product qualification

Before release, run the SupportBot journey inside Inframeld while a separate customer client keeps using its original endpoint. Demonstrate the following behavior:

| Area | What to demonstrate |
| --- | --- |
| **CLI and account recovery** | Closing and reopening the CLI follows existing work without duplication. Canceled/expired browser login and recovery remain safe. Studio recovery is deferred with Studio. |
| **Immutable inputs** | Later edits do not change the inputs of an admitted build or run. |
| **Pre-build querying** | Direct Pipeline queries and evaluation execute fixed captured working-configuration inputs with verified dependencies, without creating a release version, production feedback or publication authority. |
| **Policy-controlled Build** | Capture saved configuration and the reviewed target/mode once. Distinguish ready output from publication, and reject ambiguous selection or changed consent. |
| **Evaluation history** | Changed benchmark and evaluator identities are labeled, and partial judge failure is handled. |
| **Permissions** | Permission changes are respected. Deployment-only Query cannot invoke a direct Pipeline query. An application with explicit Query on that Pipeline may do so. Neither Query grant implies trace inspection, Build or release authority. |
| **Canary routing** | Affinity cohorts remain stable under the required integration contract. |
| **Release transitions** | Rejection before promotion and rollback after promotion behave correctly. Unavailable targets are handled. |
| **Concurrent operators** | Two operators racing cannot silently overwrite one another's release decisions. |
| **Evaluation versus release authority** | Passing a metric never triggers a Deployment pointer change. |

| Scenario | Expected outcome |
| --- | --- |
| A route or model changes | Regenerate the contract. Drift checks detect an outdated artifact. |
| A client cannot handle native nullable or union schemas | Resolve client compatibility. Do not relabel the schema as OpenAPI 3.0.3. |
| A public docs request succeeds | It reveals no tenant data, secrets, or internal operational details. |
| Studio makes a server-side request | It preserves the current user's context without a shared administrator key. |
| An answer response is lost | The documented retry returns the original receipt outcome, without another paid query. |

<a id="separate-a-trial-from-qualified-capacity"></a>

<a id="capacity"></a>

<a id="6-separate-a-trial-from-qualified-capacity"></a>

## Separate a trial from qualified capacity

The proposed trial workload is **100–200 small text-native documents**, around **1,000–2,000 chunks**, one embedding profile, one active query, and one parser job.

The planning machine is a 16 GiB laptop with roughly four CPUs and 8 GiB of memory assigned to Docker, plus 50 GiB of free disk. Models run remotely or through the customer's gateway.

OCR, large tables, local language models, and concurrent evaluations can require substantially more resources.

These trial figures have not been tested. [Indexing qualification](#qualification) defines the larger proposed test: 25,000 documents, 500,000 vectors, and two shards. Measure complete updates and queries, including membership checks, verification, and cleanup. No million-document capacity is established. Backend development can begin before this work is complete, but production capacity claims cannot.

<a id="measure-this-workload-rather-than-borrowing-a-vendor-result"></a>

### Measure this workload rather than borrowing a vendor result

To measure Inframeld's storage behavior, record the hardware, object sizes, concurrency, checksum handling, durability settings, and server/SDK versions. Otherwise the results are difficult to reproduce or compare.

Measure uploads, reads, limited-size manifest operations, repeated small-corpus updates, deletion, memory peaks, and backup/restore time. Also measure **disk amplification**, the storage consumed beyond the logical input, and **p95 latency**, the duration within which 95% of observed requests finish.

A large sequential-transfer result does not predict thousands of small manifest operations. Parsing, embedding, or Chroma may dominate total build time, but that remains an assumption until measured.

<a id="measure-the-full-first-use-journey"></a>

<a id="7-measure-the-full-first-use-journey"></a>

## Measure the full first-use journey

The first-answer goal measures usability. Two minutes is an aspiration, and roughly ten minutes is acceptable too. Neither is a hard gate or promised support limit. A timer is no reason to weaken correctness or add infrastructure.

<a id="use-a-small-explicit-fixture-and-prepared-environment"></a>

### Use a small, explicit fixture and prepared environment

A **fixture** is a defined set of test inputs used to repeat the scenario.

| Part of the scenario | Assumption or bound |
| --- | --- |
| **Documents** | Two UTF-8 Markdown/plain-text files, each at most **25 KiB**, about **10 chunks combined**, with a hard test cap of **20 chunks**. UTF-8 is the text encoding used by the files. |
| **Retrieval evidence** | Include facts absent from the question, such as a fictional product’s exact refund period and installation port. Success must depend on retrieving them. |
| **Excluded document work** | PDFs remain supported elsewhere, but scanned PDFs/OCR, tables, and larger documents are outside this timing scenario. |
| **Proposed host** | A laptop with **16 GiB RAM**, roughly **four CPUs and 8 GiB available to Docker**, local SSD, and the existing small-trial disk allowance. These are proposed test assumptions, not measured minimum requirements. |
| **Concurrency** | One user and one parser job, with no concurrent builds/evaluations and no local language-model or cross-encoder loading. |
| **Prepared installation** | Product images and pinned parser text assets are already downloaded. Application volumes are empty, so migrations, account setup, and default provisioning still happen. |
| **Protected configuration** | The operator supplies persistent encryption/bootstrap secret files through normal one-time installation preparation. This is a stated prerequisite, not a substitute for saving provider credentials in the application. |
| **Model endpoint** | An available, pre-approved endpoint, with valid credentials at hand. Configure embedding and generation separately, sharing a connection where appropriate. No judge is needed. |

This scenario assumes the endpoint origin and certificate authority are already approved. A private gateway needing extra certificates or network setup has a separate cost to measure. It cannot be promised the same setup time.

Measure optional role probes when selected, embedding, and generation, noting throttling and provider cold starts. Record whether preflight was chosen or skipped. Do not prescribe mandatory seconds per stage before measuring an implementation.

<a id="report-three-different-journeys-rather-than-substituting-the-easiest-one"></a>

### Report three different journeys rather than substituting the easiest one

| Journey | What its clock includes |
| --- | --- |
| **Prepared installation launch → first answer** | Start when the user launches the already-installed product, before services are healthy. Include startup/migrations, account/private-resource setup, model/credential entry and any selected probes, upload, parsing/chunking, embeddings, index verification, authorized publication, and question generation. Include human interaction time. |
| **Clean installation → first answer** | Also include obtaining Docker if absent, image/model downloads, generating initial protected configuration, and host/network setup. Report these real first-run costs rather than moving them outside both clocks. |
| **Restart with existing accounts/configuration → answer** | A separate, easier case. It must not replace the empty-application-state journey. |

Image downloads alone can exceed two minutes, so do not claim that timing from a fresh machine. Report automated phases separately. A test that supplies configuration instantly does not measure a human completing onboarding.

Investigate slow service startup or migrations, credential entry, parser startup, and provider cold starts or rate limits. Prepare assets, limit text processing, explain model roles, and reuse connections where authorized. Offer the optional reranking choice through the same role/model/connection screens. Built-in or none needs no new key. Keep optional OCR and post-setup generator/judge configuration outside the required first-answer path.

Authentication, parser isolation, index verification, and real supporting evidence remain required. Use measured delays to improve confusing or slow steps. A longer run alone is not a reason to redesign the architecture.

<a id="lightweight-end-to-end-acceptance-scenario"></a>

### Lightweight end-to-end acceptance scenario

1. **Start with prepared images and empty application state.** Start the full journey clock. Complete real account setup and save actual role configurations and a credential through the API-backed flow. Exercise the path with preflight skipped and record that choice. Unknown profile settings must still be supplied before the build.
2. **Upload the complete two-file batch with Automatic updates selected.** Its admission authorizes the ordinary build and first publication without a separate Prepare and ask command. Record source versions, collection revision, job/build, ready PipelineVersion, and the actual first Deployment. Verify that no Deployment existed before readiness.
3. **Ask for a fixture-specific fact.** The answer must match permitted retrieved content, contain valid source citations and an answer identity, and use the real `ModelGateway` and Chroma paths. Verify separate validation evidence from actual embedding and generation calls without extra synthetic requests. A canned answer or ungrounded fallback does not pass.
4. **Report the full journey, not only the fastest run.** Repeat a few clean-application-state runs. Record total and phase times, available provider model/revision, chunk counts, hardware, and image versions. Check whether a new user completes the path without learning internal resource setup. Neither two minutes nor roughly ten minutes is a hard gate or promised support limit.
5. **Check the essential behavior separately.** Verify that restart preserves credentials and default IDs, another user cannot read starter data, and retries do not duplicate setup. Failed batches must never publish. Cancellation or a control change must prevent an old build from publishing. A failed later update must leave healthy P1 serving. Check API/MCP default resolution and feedback attribution against the actual version. Retry an alias query after promotion or rebinding and confirm it returns the original operation/receipt without another model call.

During backend-first work, authenticated integration tests and a test client can check behavior and server timings. Measuring a real person's discovery and setup journey requires the CLI and its small Ory browser account UI. Both can be qualified independently of full Studio. Future Studio has its own generated-client and browser gates.

V1 qualifies the CLI journey and its independent Ory account UI without requiring full Studio. Generated-client compatibility follows the delivered contract incrementally. This is a focused acceptance exercise rather than a new certification or operations program. See [V1 scope](v1-scope-and-extension-boundaries.md).
