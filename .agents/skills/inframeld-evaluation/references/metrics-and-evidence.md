# Explain what a score actually measures

Alice changes chunking and gets a different score. Before calling it a regression, identify what was measured, which cases were eligible and whether source passage identity remained reconstructible. A missing coordinate mapping is not the same as retrieval failing to find a passage.

## Passage identity and coverage

Expected passages retain source version, parsed-artifact identity, source spans and reconstructible protected evidence, including generation-scenario attribution. Indexing supplies coordinates for the text actually returned, including any truncation.

Measure full union coverage at each named stage. Two chunks may together cover one expected passage even when boundaries changed. Chunk IDs, filenames and fuzzy resemblance do not prove equivalent passage identity.

Report missing mappings as unscorable counts separately alongside the scored denominator. For example, 16 covered cases among 19 mappable cases and one unscorable case are reported as 16/19 plus one unscorable, not 16/20. This is an illustrative calculation, not a measured result.

## Faithfulness uses the final context

Questions go through the ordinary Pipeline without reference answers or expected passages. The judge receives the final context actually sent to generation as support evidence. Expected/reference evidence must not add missing support to the judge's input.

Ragas faithfulness is supported claims divided by evaluated claims for each eligible case, followed by the mean of successfully scored eligible cases. For an illustrative answer with two supported claims out of three evaluated claims, the case score is two-thirds. This example is arithmetic, not measured product performance.

Report the denominators and successfully scored population. Abstention, missing evidence, no extracted claims and malformed judgments cannot become perfect scores. Preserve failures, exclusions and paired comparison coverage.

Passage coverage, citations, outcome, latency and usage answer different questions and must remain distinct signals.

## Read results responsibly

Keep answering progress separate from scoring progress. Show real counts, saved results and incomplete cases without hiding failures or exposing protected populations. Compare like observations and identify missing pairs instead of reducing the benchmark silently.

A score claim should identify the metric definition, corpus, current access, evaluator/judge configuration, paired cases and missing observations. Human calibration must assess claim extraction and support judgments. Source-inspected Ragas compatibility is not calibration or executed integration.

## Status and sources

Evaluation supplies offline evidence, not release authority. Historic scores keep their original meaning. Source erasure can remove reconstructible evidence. Do not infer quality approval, automatic mode changes or mandatory evaluation before first use.

- [Passages](../../../../docs/development/evaluation.md#passages), [metrics](../../../../docs/development/evaluation.md#metrics), [human calibration](../../../../docs/development/evaluation.md#qualification), [result presentation](../../../../docs/development/evaluation.md#result-presentation), [Indexing](../../../../docs/development/indexing.md) and [Evaluation records](../../../../docs/development/data-model.md#evaluation).
- [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) owns the selected claim-based metric, gateway boundary and qualification limits.

## Pending decisions for dependent implementation

The ordinary behavior above remains owned by its current sources. Before choosing an unresolved implementation contract, load only the matching entry:

- [PD-INDEXING-03: Keep source passage identity stable when chunking changes](../../inframeld-indexing/references/decision-source-coordinates.md). Before defining parsed artifact identities, source-span fields, chunk transformation mappings or passage-coverage implementation.
- [PD-EVALUATION-02: Coordinate fixed runs and expose honest protected results](decision-run-and-result-contracts.md). Before defining run/comparison inputs, durable progress, scoring outcomes, result inspection or summary/export schemas.
- [PD-EVALUATION-03: Qualify embedded Ragas without hidden calls or false confidence](decision-ragas-integration-and-calibration.md). Before implementing embedded generator/judge adapters or claiming supported model-quality/calibration results.
