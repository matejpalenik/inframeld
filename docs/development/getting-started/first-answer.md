# Understand the first-answer journey

<a id="understand-the-first-answer-journey"></a>

Alice wants SupportBot to answer from the handbook. This page describes the accepted product journey. The current backend has authentication, grant and recovery foundations. The complete Rust CLI, onboarding, indexing and answer journey are not delivered merely because they are described here. For what you can start today, use [local setup](local-setup.md).

1. Sign in through the browser-assisted CLI path and resolve the same local human.
2. Resume ordinary private starter resources with explicit grants.
3. Review model connections, credentials and spending controls.
4. Admit complete document bytes and select a complete collection revision.
5. Prepare verified search data, then publish through separately authorized release controls.
6. Ask a question under current permissions and retain a content-free receipt.

<a id="follow-the-first-answer-and-a-later-change"></a>

<a id="journey"></a>

<a id="6-follow-the-first-answer-and-a-later-change"></a>

## Follow the first answer and a later change

Alice completes account setup, saves a provider connection, and selects embedding model **E** and generation model **G**. Her private default starts in Automatic updates.

She completes one batch containing `installation.md` **A1** and `refunds.md` **B1**. The worker builds **P1** against **R1 = {A1, B1}**, then the separate publication command creates the first Deployment and binds the route.

The client shows preparation progress, then **Ready to ask**. Her answer has normal citations and **AnswerReceipt A77**. No judge or release screen is required.

<a id="finish-setup-before-optional-evaluation"></a>

### Finish setup before optional evaluation

In the CLI starter-evaluation journey, **Finish** is the default action after the first answer. Asking another question, inspecting the execution, or generating starter evaluation cases are optional. Choosing Finish leaves a fully usable pipeline. It creates no evaluation job or judge configuration.

If Alice chooses starter generation, she selects an existing generator connection, reviews the permitted source sample, outgoing data, estimated cost and budget, then admits a separate durable job. The default request is 20 single-passage cases. They are unreviewed proposals, with exact source excerpts and proposed answers, not automatically trusted tests. Review can be deferred or resumed without running a judge.

Only a later explicit evaluation action selects a judge and freezes accepted case revisions into the default regression benchmark. Neither action modifies the pipeline's generation model or publication mode. Rejected drafts, partial generation, budget exhaustion, and changed permissions follow [Evaluation](../../../.agents/skills/inframeld-evaluation/references/generation-and-review.md), the canonical lifecycle specification. The Ragas integration and these CLI commands remain accepted design pending implementation and qualification.

<a id="successful-replacement"></a>

### Successful replacement

Alice admits **B2**, then explicitly authorizes the complete selection **R2 = {A1, B2}**. The authorized live-input update captures that revision with the Deployment-selected configuration. [Collection selection](../../../.agents/skills/inframeld-knowledge/references/collection-selection-and-batches.md) is separate from admitting bytes. P1 continues serving during the build. After verification and eligible publication, **P2 becomes current and P1 becomes previous**.

Feedback submitted later for A77 still belongs to P1.

<a id="failure-and-overlapping-updates"></a>

### Failure and overlapping updates

The next batch requests P3, but the build fails. Healthy P2 keeps serving. If a newer authorized batch replaces P3's request while it retries, P3 cannot publish later. The newest complete selection is handled next.

Show failure of the newest update. Do not silently publish an incomplete corpus or fall back to an older request that was replaced.

<a id="manual-review"></a>

### Manual review

Alice can query and evaluate a changed working configuration while Production remains automatic. Those operations do not publish. If she also wants to stop independently authorized live updates during review, she switches to Manual releases, removing pending automatic jobs' permission to publish. She compares her captured working settings freshly against P2, explicitly saves the settings she wants, then builds P4 from the current saved configuration. Build discloses any mismatch with evaluated inputs. She may compare the ready P4 again, then attach a candidate and promote or reject it, with optional canary traffic.

Enabling automation while that candidate remains attached is rejected. A later rollback leaves Manual releases selected.

<a id="automatic-again"></a>

### Automatic again

After resolving the candidate, Alice selects Enable automatic updates and apply pending changes. She reviews the selected corpus and settings and authorizes fresh work. Current keeps serving while it builds. Previously disabled jobs remain unable to publish.

The route, permissions, data, and historical evaluations remain the same ordinary resources throughout.

Follow [first use and private defaults](../../../.agents/skills/inframeld-architecture/references/first-use-and-private-defaults.md) for provisioning and retries, or the [document-to-answer journey](../../../.agents/skills/inframeld-architecture/references/document-to-answer.md) for responsibilities. A longer first run cannot justify weaker authorization, parser isolation or verification.
