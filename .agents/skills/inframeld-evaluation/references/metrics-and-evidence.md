# Explain what a score actually measures

<a id="explain-what-a-score-actually-measures"></a>

Alice changes chunking and gets a different score. Before calling it a regression, identify what was measured, which cases were eligible and whether source passage identity remained reconstructible. A missing coordinate mapping is not the same as retrieval failing to find a passage.

<a id="read-results-responsibly"></a>

## Apply accepted PD-EVALUATION-02

Accepted [PD-EVALUATION-02](decision-run-and-result-contracts.md#approved-resolution) selects this workflow's detailed contract. A run can answer successfully while a metric cannot be calculated. A comparison can also have missing pairs. Those facts must remain visible instead of collapsing into one success flag or score. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Choose a focused reading task

- For coverage calculation and missing mappings, read [Passage coverage](passage-coverage.md).
- For claim scoring and judge failures, read [Faithfulness](faithfulness.md).

## Read results responsibly

Keep answering progress separate from scoring progress. Show real counts, saved results and incomplete cases without hiding failures or exposing protected populations. Compare like observations and identify missing pairs instead of reducing the benchmark silently.

A score claim should identify the metric definition, corpus, current access, evaluator/judge configuration, paired cases and missing observations. Human calibration must assess claim extraction and support judgments. Source-inspected Ragas compatibility is not calibration or executed integration.

<a id="keep-metrics-separate"></a>

<a id="metrics"></a>

<a id="5-keep-metrics-separate"></a>

## Keep metrics separate

| Signal | Interpretation |
| --- | --- |
| **Passage coverage** | Stage-specific full expected-passage coverage, defined in [Passage coverage](passage-coverage.md). |
| **Faithfulness** | Per-case claim fraction and macro mean, with eligible, scored, failed, and unscorable counts. Support does not establish completeness, relevance, or truth outside the supplied source. |
| **Citation presence/validity** | Answered cases with at least one valid backend-derived citation divided by answered cases. Count invalid citations separately. Identities must resolve to that execution's permitted evidence. Valid IDs do not prove claim support. |
| **Execution outcomes** | Answers, explicit abstentions, failures, cancellations, and unattempted cases across all admitted cases. Pipeline and judge failures remain distinct. |
| **Latency** | Query p50 (median) and p95 (95th percentile), with sample counts for completed answers/abstentions. Report failures/timeouts, judge time, and total time including queueing separately. Small samples do not establish production latency. |
| **Usage/cost** | Gateway calls, tokens, and observed/estimated charges, separated by pipeline execution, starter generation, and judging. Unknown values are not zero. |

There is no blended quality score. Show each denominator and exclusions. Completion says whether work finished, not that every metric was available or the pipeline passed.

<a id="result-presentation"></a>

<a id="make-progress-and-results-easy-to-inspect"></a>

### Make progress and results easy to inspect

For example, a 20-case run can finish with 18 answers, one explicit abstention and one failed query. If scoring failed for one of the 18 answers, faithfulness covers 17 answers, not 20. A result summary must identify that saved-but-unscored answer separately from the query that failed. "No answer returned" means an explicit pipeline abstention here, not a missing network response.

CLI progress and result presentation presents those facts in ordinary language. Keep the admitted population, answering/scoring progress, per-case outcomes and saved results visible. In-progress counts name their denominator. "12 answered. 10 of those 12 scored" does not mean the other eight admitted questions have run. At completion or interruption, retain stage-specific passage coverage, faithfulness and its scored population, citation signals, failures/exclusions, latency sample counts and known/estimated/unavailable usage. The concise view may put additional stage, claim and pipeline-versus-judge details behind normal result inspection, but may not conceal missing observations or substitute a combined pass score.

Show a bounded list of cases needing attention, with stable case identity, permitted question text and a short reason such as "Answer saved. Scoring failed", "Query failed" or "Not started". Make the full authorized list and individual saved answers/evidence available through ordinary paginated history inspection. Long questions can be shortened in the summary and read in full in the case view. Failed queries, abstentions, judge failures, canceled work, unscorable evidence and uncertain dispatch are different outcomes. Question text, identifiers and aggregate counts are protected too. Never reveal an inaccessible population or reconstruct erased content for a friendly screen.

A budget stop with 17 fully completed cases and three not started retains the 17 results and names the remaining cases when permitted. If instead case 18 has an unknown paid-call outcome, identify that uncertainty and the two not-started cases. Do not label all three safe to retry or suggest ordinary resume. Apply [job recovery](../../inframeld-application-contracts/references/cli-result-contracts.md#progress-presentation) without repeating completed or uncertain model calls. Reading results never runs the pipeline or judge to fill missing data.

Reuse Evaluation's existing logical case/run observations and shared jobs. This is not a new data framework, generic work-item registry or status enum. Evaluation must define exact representations, persist outcomes and expose protected reads. Human and JSON presentation need the same qualified meanings. Contract and runtime qualification remain required.

<a id="maintainer-checks"></a>

<a id="11-maintainer-checks"></a>

## Maintainer checks

| Walkthrough | Expected outcome |
| --- | --- |
| Evaluate before any release-ready version exists | Capture captured working-configuration inputs, prepare verified dependencies and run explicitly without publication authority. |
| Edit working settings while evaluation runs | All cases keep the admitted effective configuration and corpus. Subsequent edits affect later requests only. |
| Change selected shared access settings while evaluation runs | Stop further model dispatches. Preserve partial results and actual revision attribution. A new explicit admission is required, with both comparison sides executed freshly. |
| Compare working settings with a live baseline | Resolve the baseline once, execute both sides freshly, and never follow changing live pointers per case. |
| Build after a temporary override or a sample test | Build uses saved settings and selected build corpus, discloses mismatches and does not claim the earlier run approved them. |
| Finish after setup | Pipeline remains usable. No generator, judge, tests, or evaluation charges required. |
| Reject every draft | No default benchmark can run. Explain the absence of accepted cases. |
| Edit after benchmark freezing | New revision unreviewed. Old snapshots unchanged, subject to erasure. |
| Change chunking | Complete mapped coverage can pass without equal chunk IDs. |
| Mapping unavailable | Unscorable, not ordinary retrieval miss. |
| Twenty cases produce 16 found, three misses and one unavailable mapping | At that named stage show 16/19 scored, the unscorable case and the original 20-case scope when permitted. Do not shrink the benchmark or reuse that denominator for other metrics. |
| Historical execution binding disappears while a newer document/index exists | Report unavailability and preserve permitted partial results, without replacing or rebuilding the selected historical input. |
| Reference answer exists for a cancellation question | Execute only the question through ordinary Pipeline inputs. Expected text cannot be injected into retrieval/generation or used as extra faithfulness support. |
| Revoke access during work/before history inspection | Stop prohibited sends and deny protected content, keeping safe partial status. |
| Erase a source | Derived protected test/evaluation content becomes unavailable under cleanup policy. |
| Unsupported selected model | Clear capability/output failure. No fallback. |
| Exhaust budget | No new paid dispatch. Completed drafts/results and incomplete counts remain visible. |
| Cancel during keyphrase preparation | Cancellation applies there too, before a final executor handle exists. |
| Obtain 17 of 20 requested cases | Save 17 unreviewed drafts and report three missing/failed units. No unbounded regeneration. |
| Lose a provider response | Uncertain-outcome recovery, never silent replay of a potentially paid call. |
| Candidate judge fails once | Show failure and smaller paired coverage, not a false improvement. |
| Disable project tracing | No library export bypass. Explicit evaluation records have their separately disclosed lifecycle. |

<a id="pending-decisions-for-dependent-implementation"></a>

## Decision references for dependent implementation

Apply the accepted entries when their scope matches. Evidence and implementation remain separate:

- [PD-INDEXING-03 (accepted): Keep source passage identity stable when chunking changes](../../inframeld-indexing/references/decision-source-coordinates.md). Before defining parsed artifact identities, source-span fields, chunk transformation mappings or passage-coverage implementation.
- [PD-EVALUATION-02 (accepted): Coordinate fixed runs and expose honest protected results](decision-run-and-result-contracts.md). Before defining run/comparison inputs, durable progress, scoring outcomes, result inspection or summary/export schemas.
- [PD-EVALUATION-03 (accepted): Qualify embedded Ragas without hidden calls or false confidence](decision-ragas-integration-and-calibration.md). Before implementing embedded generator/judge adapters or claiming supported model-quality/calibration results.

<a id="status-and-sources"></a>

## Status and sources

Evaluation supplies offline evidence, not release authority. Historic scores keep their original meaning. Source erasure can remove reconstructible evidence. Do not infer quality approval, automatic mode changes or mandatory evaluation before first use.

- [Passages](passage-coverage.md#passages), [metrics](#metrics), [human calibration](gateway-and-jobs.md#qualification), [result presentation](#result-presentation), [Indexing](../../inframeld-indexing/references/profiles-and-preparation.md) and [Evaluation records](records.md#evaluation).
- [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) owns the selected claim-based metric, gateway boundary and qualification limits.
