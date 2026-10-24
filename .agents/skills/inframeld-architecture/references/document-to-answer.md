# From a document to an answer

Alice wants to ask questions about two Support documents, A1 and B1. The goal is a useful private answer with enough evidence to understand later changes. The following journey describes accepted behavior. Individual operations still need their stated implementation and qualification.

## Owners along the journey

```mermaid
flowchart LR
    Access["Access<br/>Identify and authorize"] --> Knowledge["Knowledge<br/>Admit exact versions"]
    Knowledge --> Indexing["Indexing<br/>Prepare and verify"]
    Indexing --> Pipeline["Pipelines<br/>Build ready output"]
    Pipeline --> Releases["Releases<br/>Select traffic"]
    Releases --> Answer["Pipelines<br/>Answer and record receipt"]
    Indexing --> Evaluation["Evaluation<br/>Review and compare fixed inputs"]
    Evaluation -.->|"Evidence for a human decision"| Releases
```

Arrows show a product journey, not automatic authorization or code dependencies. Access checks also occur at later protected boundaries. Evaluation can run against captured working inputs before a release build, and its scores never authorize a release.

## Follow Alice

1. Alice authenticates. A separately authorized host claim establishes the first administrator when needed. Product admission and explicit grants remain separate from identity and OAuth consent. Private starter resources are ordinary resources. Alice is explicitly both member and manager of the starter group.
2. She configures the actual model roles and approved destinations. A saved provider secret supplies outbound authentication. Optional synthetic preflight can help, but complete valid configuration may be used without a separate test call. Real calls retain mandatory security and response checks.
3. Knowledge admits a complete bounded upload through private staging. It preserves logical source identity, immutable byte versions and explicit nonempty document audiences. Partial bytes or an incomplete batch cannot become a live corpus.
4. Indexing processes admitted versions, obtains embeddings through ModelGateway and verifies exact search bindings. Upload success, parsing success and searchable readiness are different states.
5. Alice may query the Pipeline's working settings and evaluate captured inputs. No Experiment resource or release-ready PipelineVersion is required for this development loop. Temporary overrides do not save settings or publish traffic.
6. Build captures saved configuration and exact corpus inputs. Ordinary preparation creates a ready version. Target-specific publication has its own authority and current checks.
7. A query to Production selects the serving version, protects its dependencies with a bounded pin, retrieves currently permitted evidence and generates through ModelGateway. The live answer's receipt retains exact attribution, including final evidence that was not cited.

The default serving path starts in Automatic updates. Explicitly created Deployments default to Manual releases with an automatic option at creation.

Automatic work still needs the underlying mutation rights, Build and the target's release authority. Before a default Deployment exists, first publication has its separately authorized creation path.

## What changes and what stays fixed

Replacing B1 creates B2 and revision R2={A1,B2}. Earlier R1={A1,B1} remains fixed. Indexing can reuse A's compatible search data. An admitted query or evaluation keeps its captured inputs while Alice edits the working Pipeline.

A failed build leaves healthy current traffic in place.

Switching Automatic to Manual invalidates old publication authority. Switching back admits fresh work and cannot revive the old job. Canaries and rollback require Manual mode.

Erasing B is stronger than omitting it from a new collection. Current access and publication are blocked before resumable physical cleanup. A historical version may become unavailable. Frozen history never promises permanent content retention or current permission.

If an answer response is lost, retry finds the original operation after current authentication and authorization. It returns the documented receipt-only outcome instead of another paid generation. Evaluation and direct-query records do not enter production feedback statistics.

## Status and sources

Setup requires neither a benchmark nor a judge. First-answer timing is flexible and unmeasured here. No diagram, default preset or historical evidence weakens access, verified readiness or paid-call uncertainty handling.

Read [Onboarding](../../../../docs/development/onboarding.md), [Knowledge](../../../../docs/development/knowledge-lifecycle.md), [Indexing](../../../../docs/development/indexing.md), [Pipelines and Releases](../../../../docs/development/pipelines-and-releases.md), [Evaluation](../../../../docs/development/evaluation.md), [Feedback](../../../../docs/development/answer-feedback.md), and [Jobs](../../../../docs/development/jobs-and-idempotency.md) for exact rules. [ADR-0052](../../../../docs/adr/ADR-0052-separate-experimental-execution-from-release-ready-pipeline-builds.md) explains the pre-release development loop.
