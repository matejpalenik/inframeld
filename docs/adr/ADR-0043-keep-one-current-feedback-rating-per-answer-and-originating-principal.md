# ADR-0043: Keep one current feedback rating per answer and originating principal

Status: Accepted

**Date:** 2026-09-19

## Context and Problem Statement

A user may correct a rating, and feedback can arrive after the serving deployment has changed. Counting submissions as independent votes would distort the evidence and lose its original context.

## Considered Options

- One editable current rating attached to an answer receipt and originating principal.
- Append a new independent vote for every submission or retry.
- Attach late feedback to the deployment version that happens to be current now.

These options summarize the recorded choices, exclusions, and deferrals. They do not imply an additional comparison or benchmark was performed during this rewrite.

## Decision Outcome

Keep one current rating per answer and originating principal, with the accepted bounded comment and revision behavior. Preserve the answer’s original version, deployment state, and evidence attribution through its receipt. Protect feedback and reporting with current access and the receipt’s retention rules. Feedback is informative and cannot authorize a release.

**Example.** Correcting a negative rating to positive replaces that answer’s current rating. It adds neither a second rated answer nor another vote.

## Consequences

- Corrections and retries do not inflate votes, and results remain attributable to what actually answered.
- Inframeld verifies the submitting application, not every human behind it. Self-selection, incomplete history, and visible denominators limit conclusions drawn from feedback counts.

## Links

Implementation evidence and qualification limits are recorded in the current guides below. This ADR records the design choice; the editorial rewrite did not verify runtime behavior.

- [Current answer feedback](../development/answer-feedback.md).
- [Current data model](../development/data-model.md).
