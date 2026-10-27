# Evaluation architecture: compare fixed inputs with honest evidence

<a id="evaluation-architecture-compare-fixed-inputs-with-honest-evidence"></a>

Alice changes a reranker and wants to know whether answers improve. She needs the same reviewed questions on both sides, fresh execution and clear reporting when a case cannot be scored. An old score or a missing result cannot silently become evidence that the new configuration is better.

<a id="what-evaluation-owns"></a>

## What Evaluation owns

Evaluation owns generated cases, review, immutable case revisions, benchmarks, evaluator revisions, runs, comparisons and protected history. A benchmark fixes case membership and revisions. An evaluator revision fixes how observations are scored. A comparison executes two selected configurations against the same frozen benchmark and evaluator.

Knowledge supplies source identity. Indexing supplies processed passages and coordinates. Pipelines executes ordinary questions. Access protects current source and result access. ModelGateway controls every remote generator, judge and repair call. Evaluation supplies evidence, while Releases retains publication authority.

<a id="main-parts-and-boundaries"></a>

## Main parts and boundaries

**Accepted responsibility view.** Ragas is an embedded library behind application adapters, not a separate service or owner of durable state.

```mermaid
---
title: "Evaluation responsibilities - accepted design"
---
flowchart TB
    Corpus["Permitted processed sources"] -->|"Bounded sample across sources"| Generation["Case generation"]
    Generation -->|"Unreviewed proposed questions and evidence"| Review["Case review and immutable revisions"]
    Review -->|"Freeze selected accepted revisions"| Benchmark["Benchmark and evaluator inputs"]
    Benchmark -->|"Admit exact baseline and candidate"| Runs["Run and comparison coordination"]
    Runs -->|"Questions without reference answers"| Pipeline["Ordinary Pipeline execution"]
    Pipeline -->|"Actual answers, stages and final context"| Metrics["Passage coverage and faithfulness scoring"]
    Generation -->|"Remote synthesis"| Gateway["ModelGateway"]
    Metrics -->|"Remote judgments and bounded repairs"| Gateway
    Metrics -->|"Outcomes, denominators and missing pairs"| History["Protected results and history"]
```

Arrows show data and execution responsibilities. Generation proposes cases. Review accepts particular revisions. Generation, review and evaluation are separate explicit operations. An evaluation executes questions and scores eligible observations. Setup can finish without any of them.

<a id="follow-a-fresh-comparison"></a>

## Follow a fresh comparison

**Accepted target workflow.** Both sides may be ready versions or captured working inputs. Neither requires a new release build merely to compare settings.

```mermaid
---
title: "Fresh comparison - accepted execution contract"
---
sequenceDiagram
    actor Alice
    participant E as Evaluation operation
    participant A as Access
    participant J as Durable job and results
    participant P as Ordinary Pipeline
    participant I as Indexing and recorded bindings
    participant S as Scoring adapters
    Alice->>E: Compare baseline and candidate
    E->>A: Require current run authority and protected scope
    E->>J: Admit exact inputs, benchmark, evaluator and role bindings
    Note over E,J: Later edits cannot change admitted membership or settings
    alt Newly captured working inputs
        J->>I: Ordinary authorised preparation of complete bindings
    else Retained input snapshot or ready version
        J->>I: Verify recorded bindings remain available
        Note over J,I: Missing historical bindings fail, no rebuild or substitution
    end
    loop Both sides, each selected case with usable execution inputs
        J->>P: Execute question with captured inputs
        Note over P: Current access, complete bindings and gateway rules apply
        P-->>J: Actual outcome and permitted evidence
        J->>S: Score stage passages and actual final context
        alt Missing verified passage mapping
            S-->>J: Affected metric unscorable with reason
        else Eligible observation
            S-->>J: Metric result with its denominator
        end
        Note over J: Preserve failures and partial progress under current access
    end
    J-->>Alice: Protected comparison with paired coverage and exclusions
```

The diagram's result step also requires current inspection authority. Run authority alone does not grant result inspection. An execution failure or lost source access remains an explicit outcome. It does not permit substituting a newer corpus or silently dropping a case. An unavailable historical binding is not rebuilt to make an old input appear runnable.

Faithfulness asks whether the answer's claims are supported by the final context actually supplied to generation. Reference answers and expected passages are evaluation inputs only. They must not leak into Pipeline execution or add missing support to the judge. Passage coverage is a different metric. For example, 16 covered cases among 19 mappable cases plus one unscorable case is 16/19 with one unscorable, not 16/20.

<a id="data-and-execution"></a>

## Data and execution

PostgreSQL retains selected identities, progress and permitted results. Protected source-linked content remains subject to current audiences, source access and erasure. Fixed inputs do not freeze permission or guarantee permanent evidence availability.

Durable jobs save accepted work and progress across watcher disconnection or restart. Preparation and per-case work are bounded. Provider calls stay outside SQL transactions. All nested generation, judging and repairs use ModelGateway. A paid timeout does not authorise automatic redispatch.

Relevant connection-access changes stop later dispatch and identify interrupted or changed-environment evidence. Credential-only rotation and metadata-only rename retain their specific exceptions. Both comparison sides execute freshly rather than subtracting historical scores. Paired coverage identifies cases with comparable observations on both sides. Show missing pairs and their outcomes alongside that population rather than shrinking the benchmark silently.

<a id="what-exists-today"></a>

## What exists today

This is accepted Evaluation design. Ragas compatibility was source-inspected as recorded by the guide, but no Evaluation module, runtime integration or human judge calibration is established by this view. The logical records do not mandate physical tables or one aggregate per concept.

Read [generation and review](generation-and-review.md), [benchmarks and comparisons](benchmarks-and-comparisons.md), [metrics and evidence](metrics-and-evidence.md), [gateway and jobs](gateway-and-jobs.md) and [history and transfer](history-and-dataset-transfer.md) for their own limits.

<a id="decisions-still-needed-and-sources"></a>

## Decisions still needed and sources

[ADR-0078](../../../../docs/adr/ADR-0078-separate-evaluation-case-work-run-coordination-and-scoring.md) accepts focused case generation/review operations, run/comparison coordination and scoring adapters. The [owning guide](#evaluation-operation-boundaries) retains exact case/run, per-metric, protected-result and bounded-progress contracts still to specify. Ragas remains embedded, with runtime integration and calibration still unqualified.

[Evaluation](generation-and-review.md), [Evaluation records](records.md#evaluation), [jobs](../../inframeld-application-contracts/references/jobs-and-recovery.md) and [model connections](../../inframeld-application-contracts/references/model-gateway-and-connections.md) own accepted behaviour and qualification.

<a id="proposed-internal-architecture---awaiting-decisions"></a>

<a id="internal-architecture-decisions"></a>

## Internal architecture decisions

The component boundaries below are accepted. They explain how to divide responsibilities inside the existing backend. The precise contracts listed with each decision remain design work. Accepted behavior elsewhere in this guide continues to own permissions, lifecycle and failure rules.

<a id="evaluation-operation-boundaries"></a> <a id="proposal-evaluation-boundaries"></a>

<a id="separate-evaluation-case-work-run-coordination-and-scoring"></a>

### Separate Evaluation case work, run coordination and scoring

**Status:** Accepted in [ADR-0078](../../../../docs/adr/ADR-0078-separate-evaluation-case-work-run-coordination-and-scoring.md), with implementation and qualification unfinished.

Evaluation separates case generation/review operations, run/comparison coordination and scoring adapters. These parts have different state, permissions and provider lifetimes. Their contracts must make progress, actual outcomes and protected results explicit.

Ordinary question execution stays with Pipelines. Durable continuation uses existing jobs, and every remote synthesis/judge/repair uses ModelGateway. Ragas remains an embedded library. Separate execution success from metric eligibility, retain fixed benchmark membership and current inspection protection, and keep publication with Releases.

**Remaining design and qualification.** Specify exact case/run inputs, per-metric outcomes, protected result representations, bounded progress and preparation/execution/scoring coordination before implementing the ports or persistence. No generic Dataset/Experiment platform, new runner or table per concept follows from this split. Runtime integration, library compatibility and human judge calibration remain qualification work.

<a id="pending-decisions-for-dependent-implementation"></a>

## Pending decisions for dependent implementation

Before choosing an unresolved implementation contract, load only the entry whose trigger applies:

- [PD-EVALUATION-01: Define exact case generation and review operations](decision-case-review-contracts.md). Before implementing case generation/review commands, revision preconditions, local acceptance or their public result contracts.
- [PD-EVALUATION-02: Coordinate fixed runs and expose honest protected results](decision-run-and-result-contracts.md). Before defining run/comparison inputs, durable progress, scoring outcomes, result inspection or summary/export schemas.
- [PD-EVALUATION-03: Qualify embedded Ragas without hidden calls or false confidence](decision-ragas-integration-and-calibration.md). Before implementing embedded generator/judge adapters or claiming supported model-quality/calibration results.
