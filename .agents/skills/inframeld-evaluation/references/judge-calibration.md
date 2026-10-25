# Qualify and calibrate the selected judge

<a id="qualify-and-calibrate-the-selected-judge"></a>

Alice sees a high faithfulness score. Before treating the judge as useful evidence, engineers compare its extracted claims and support decisions with human-labelled examples. A structured response alone does not prove a reliable judgment.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="calibrate-claim-extraction-and-support-judgments-with-humans"></a>

### Calibrate claim extraction and support judgments with humans

**Calibration** compares the selected judge with human-labelled evidence, not another model's opinion. Label factual claims and whether each is supported by the exact final context. Measure missed/altered claims separately from support-classification errors. Omitting an unsupported claim can inflate a score even when returned verdicts look valid.

Include supported and mixed-support answers, contradictions, numbers, negation, irrelevant-but-supported answers, abstentions, no-evidence/no-claim cases, long contexts, and prompt injection. Keep a held-out subset unused during tuning. Record disputed labels and denominators. Numeric acceptance thresholds must be established and tested for this rubric. The old whole-answer agreement target does not transfer automatically.

Run five fixed borderline/adversarial examples three times each, keeping all results and reporting claim/score variation, failures, calls, cost, and latency. Never select favorable repeats. Temperature zero and deterministic arithmetic do not make a judge deterministic. Recalibrate after material library, prompt, model, language, or corpus changes. Changing judge after failure is an explicit choice, not automatic fallback.
