# Score consistently and give a usable decision

Alice needs to know whether to commit a feature, which risks deserve work now and which choices can stay simple. A score cannot answer those questions without evidence and an explicit readiness decision. This reference owns the report format and calibration. It does not override the [Definition of Done](../../../../docs/development/definition-of-done.md).

## Rate the reviewed implementation

Use the same category order for a standard review. Scores assess the implementation against its current scope and standards. They do not rate the standards document itself unless requested.

| Category | Main question |
| --- | --- |
| Human maintainability | Can a person locate, understand, debug and safely modify the behavior? |
| Correctness and data integrity | Does it preserve the relevant invariants, effects and failure meaning? |
| Architecture and system design | Are ownership, boundaries, dependencies and resource lifetimes clear? |
| Scalability and evolution | Does it suit supported workloads without unnecessarily obstructing later growth? |
| Security and privacy | Are the affected trust, permission, credential and disclosure boundaries sound? |
| Test quality and evidence | Do useful, appropriately isolated tests demonstrate the claimed behavior? |
| Developer and operator experience | Can people set up, use, diagnose and recover the affected workflow? |
| Language-standard adherence | Does authored code follow the relevant repository conventions and valid exceptions? |
| Overengineering risk | How much avoidable complexity or speculative infrastructure must be maintained? |

For the first eight categories, **10 means better**. Use whole points or a justified half point. Avoid precision such as 9.27 that the assessment cannot support. Add a brief reason and evidence confidence: high, medium or low. For mixed Python/Rust work, show separate language-adherence scores within that row when their conclusions differ.

Use **N/A** for a category genuinely outside the change. Use **Not assessed** for a relevant category whose evidence was not examined, and name the gap. Neither is a perfect score. A narrow request may collapse inapplicable rows into one short scope note. Do not fabricate a broad scorecard for a behavior-only explanation.

| Quality score | Calibration |
| --- | --- |
| 1–2 | Fundamental defects or a design unsuitable for the supported task. |
| 3–4 | Major rework needed to achieve reliable, maintainable behavior. |
| 5–6 | Useful foundation with substantial correctness, clarity or maintenance gaps. |
| 7–8 | Solid within scope, with bounded improvements or qualification limits. |
| 9 | Strong and proportionate within scope, with only small remaining issues. |
| 10 | Exceptional fit to the reviewed needs, supported by strong evidence. No material improvement currently identified. |

Ten does not mean perfect under every hypothetical future requirement. Nine does not create an obligation to invent another improvement. Missing execution evidence can lower confidence without proving the architecture is poor. Conversely, a material implementation defect belongs in its relevant score even if the test suite is green.

**Overengineering risk uses the opposite direction: 1 is minimal risk and 10 is extreme risk.** Label this direction every time it appears. Scores 1–2 describe proportionate code, 3–4 describe contained unnecessary complexity, 5–6 describe meaningful avoidable maintenance burden, 7–8 describe major speculative machinery, and 9–10 describe complexity dominating the delivered need. A short but unsafe implementation is not a good overall solution simply because it has low overengineering risk.

Give one overall quality score as a reasoned judgment, prioritizing human maintainability, correctness and proportionality. Explain the limiting concern. Do not calculate an average, average the inverse risk score with quality scores, or hide a severe defect behind stronger categories. If evidence is too incomplete for a credible overall rating, say so instead of choosing an arbitrary middle score.

## Apply the maintainability bar

Ready requires overengineering risk at most **2/10, where lower is better**, and no unresolved material human-maintainability finding. This is an explicit acceptance ceiling, not a requested answer or an average of the other categories. Preserve all nine categories and their existing directions. A 9 in correctness or tests cannot compensate for a material maintenance problem.

Explain the present need, smallest safe alternative and maintenance cost of the reviewed capability, including its fixtures and execution helpers. Scores 1–2 mean the mechanism is proportionate and understandable within scope. Scores 3–4 still identify avoidable complexity and require a smaller design or implementation before Ready. Higher scores strengthen that concern. Size, language or a new helper alone does not establish overengineering. Necessary safety can require substantial code, but its implementation must remain understandable.

Support a score above 2 with concrete findings and their actual severity. A P3 preference alone cannot justify calling the whole solution materially overengineered. Conversely, do not lower a score merely because the worker explains the design, a narrow correction passed or the review was repeated. Inspect the changed source or revised plan. Unknown relevant evidence means Pending evidence, not an assumed 2. Do not infer an exception from earlier risk acceptance, general delivery authority or green CI.

When the bar is unmet, preserve the checkpoint and propose simplification, a smaller useful boundary or a separately scoped repair. If no safe maintainable option is established, explain the exact obstacle for human direction. Ordinary corrections within an accepted approach need no new ceremony. A work-in-progress checkpoint may still be saved under existing authority, but is not Ready for delivery. Required security, correctness, coverage and cleanup guarantees remain enforced.

## Findings and priorities

Findings are actionable defects or material maintenance problems supported by inspected code and a concrete scenario. Identify whether evidence is an observed result or a well-supported inference. A missing required test can be a finding without a known implementation failure when the unprotected invariant and appropriate test boundary are clear. Generic requests for more tests or best practices are not findings.

| Priority | Meaning and disposition |
| --- | --- |
| P0 | Critical harm requiring immediate action, such as demonstrated broad protected-data exposure or destructive corruption. Stop delivery. |
| P1 | Serious correctness, security or operational failure in a supported scenario. Fix before merge. |
| P2 | Material bounded defect or maintenance issue. Address in this delivery unless the developer explicitly accepts the bounded risk and follow-up. |
| P3 | Optional improvement with low impact. Keep separate from required fixes and do not make it a delivery blocker. |

State each finding as a short priority title, exact source link with verified line numbers, triggering input or operation, expected versus observed behavior, consequence and smallest remedy. Keep code-line anchors tight and use inline review comments when available. Consolidate examples sharing the same root cause. A severity label is not a substitute for explaining impact.

Do not turn formatting preferences into material findings or excuse a mandatory standard as optional taste. Explain why a convention violation matters and assign its actual impact. Do not add a fix merely to improve the score. Where a design choice is unresolved, identify its owning decision and dependency rather than pretending a preferred alternative is already required.

## Standard report

Use this order, adapting length to the change rather than adding empty headings:

1. **Findings.** Put material findings first in severity order. If none remain, say "No material findings within the reviewed scope." A long list belongs in full rather than being hidden behind an arbitrary top-three limit.
2. **Verdict and scope.** State the overall quality rating, reviewed change/base or files, material exclusions and separate readiness conclusions below. A short opening verdict may precede findings for orientation, but it must not bury a blocker.
3. **Scorecard.** Use columns Category, Score, Confidence and Basis. Apply the category order and score directions above. Give the overall score outside the table rather than a misleading arithmetic total.
4. **Design tradeoffs.** Explain the important choices to the maintainer. Name worthwhile safeguards, avoidable complexity and any costly future constraint. Say whether another refactor would produce enough present value. Avoid a mandatory praise list or a hypothetical enterprise roadmap.
5. **Evidence and limits.** Separate checks run now, earlier locally executed checks, cache results, developer/CI reports and missing evidence. Include relevant counts, skips, revision/environment and manual verification status when they change the conclusion. A finite probe is not full protocol or platform qualification.
6. **Next actions.** Separate required fixes, explicitly accepted follow-ups and optional ideas. If no additional implementation is warranted, say so. Provide a commit message only when requested, using the actual reviewed scope. Do not commit or publish it.

Use connected, plain prose and compact tables. A new reader should understand the failed user journey and proposed correction without opening a chain of architecture documents. Link the owner when a rule's status or rationale matters. Detailed code snippets follow root guidance and are unnecessary when a small recommendation suffices.

## Keep readiness decisions separate

**Commit readiness** asks whether this is a coherent change suitable for submission: reviewed implementation is understood, required local checks are satisfied or their limitation is explicit, and no known material issue is being presented as completed. A legitimate work-in-progress commit is a different user request. Required final-revision CI normally runs after a commit exists, so its absence alone cannot require changing code or forbid submission.

**Merge and issue-closure readiness** additionally checks actual issue acceptance, required final-revision CI, affected contracts/documentation and the delivery's merge status. Do not close a library foundation's owning issue only because a future executable journey sounds plausible, and do not keep it open for unrelated child-issue work already outside its accepted scope. If the issue or required checks could not be inspected, report readiness as pending rather than inventing acceptance.

Use the values **Ready**, **Changes needed**, or **Pending evidence** for each decision, with a one-sentence reason. Explicitly recorded risk acceptance can permit a bounded follow-up. High scores never override an unresolved serious defect or a failed required gate. Review is not permission to publish comments, mutate issues, commit, push or merge.

For repeated reviews, verify the prior findings against the actual current revision. Mark them resolved, still present or unverified, then review the affected boundaries for regressions. Do not carry a resolved defect forward, assume the rest is correct from a small fix, inflate ratings without evidence, or restart a full audit when nothing material changed. Maintain stable criteria so the developer can compare conclusions meaningfully.
