# Judge support in the actual final context

Alice’s generated answer contains four claims. The judge checks whether the context actually supplied to generation supports them. A reference answer is a review aid and must not be inserted into that execution or judgment as hidden evidence.

<a id="faithfulness-uses-the-final-context"></a>

## Apply accepted PD-EVALUATION-03

Accepted [PD-EVALUATION-03](decision-ragas-integration-and-calibration.md#approved-resolution) selects this workflow's detailed contract. A judging model can produce valid JSON and still miss an unsupported claim. A narrow adapter and explicit human-labelled checks make the limits inspectable. Apply its exact bounds, current-state checks and failure outcomes. Native implementation and qualification remain separate.

## Faithfulness uses the final context

Questions go through the ordinary Pipeline without reference answers or expected passages. The judge receives the final context actually sent to generation as support evidence. Expected/reference evidence must not add missing support to the judge's input.

Ragas faithfulness is supported claims divided by evaluated claims for each eligible case, followed by the mean of successfully scored eligible cases. For an illustrative answer with two supported claims out of three evaluated claims, the case score is two-thirds. This example is arithmetic, not measured product performance.

Report the denominators and successfully scored population. Abstention, missing evidence, no extracted claims and malformed judgments cannot become perfect scores. Preserve failures, exclusions and paired comparison coverage.

Passage coverage, citations, outcome, latency and usage answer different questions and must remain distinct signals.

## Calculate per case, then average

Ragas **Faithfulness** extracts factual claims from an answer, then judges whether the supplied context supports them:

```text
case faithfulness = supported claims / evaluated claims
run faithfulness = mean of successfully scored eligible case scores
```

Case scores of 3/4 and 1/1 produce a run mean of 0.875, not the pooled fraction 4/5. Keep claim denominators. The mean weights cases equally. It is not a boolean whole-answer pass rate or a confidence score.

Judge **only the final context actually sent to generation**, after reranking and whole-passage fitting. The question assists claim interpretation. Unused documents and generated reference answers cannot supply additional support. Reference-answer correctness scoring is not selected for v1.

## Failures and unscorable answers

| Situation | Required treatment |
| --- | --- |
| Explicit pipeline abstention | Faithfulness not applicable. Retain outcome. |
| Answer with no usable final evidence | Unscorable, missing-evidence input failure. Never 1.0. |
| No extracted claims, including a library NaN | Unscorable, no evaluable claims. Neither 0.0 nor 1.0. |
| Complete valid judgments mark claims unsupported | A legitimate lower score, not an execution failure. |
| Refusal, malformed/truncated output, missing/duplicate claim judgments | Judge failure. Never present a partial verdict list as complete. |
| Wrong types or non-finite/out-of-range score | Reject. No truthy-string conversion or silent clamping. |

Validate that each extracted claim has exactly one usable verdict under the pinned schema and that the score agrees with those counts. Save bounded claim text, verdicts, and explanations when produced. The inspected Ragas metric returns a score object, not a complete review record. The adapter must capture intermediate structured observations to enable inspection. Never fabricate missing explanations.

Answers and excerpts are untrusted input. Give the judge no tools, independent endpoints, or release authority. Structured output does not prevent prompt injection or prove that extraction found every claim. Calibration must test both extraction and support judgments.

## Sources and status

This is accepted metric behavior, not a qualified production judge. Read [metric interpretation](metrics-and-evidence.md) for protected result populations and [judge calibration](judge-calibration.md) before making accuracy claims. [ADR-0051](../../../../docs/adr/ADR-0051-use-ragas-for-generated-tests-and-faithfulness-evaluation.md) records the choice. Adapter and result contracts remain subject to [PD-EVALUATION-02](decision-run-and-result-contracts.md) and [PD-EVALUATION-03](decision-ragas-integration-and-calibration.md).
