# Sharing, deletion and retained evidence

Alice removes the handbook from a new corpus, changes its audience, or erases it. These actions have different effects. Omission changes future membership. Sharing changes current readers. Erasure removes the Document's versions and can invalidate retained releases and evaluation evidence.

## Change an audience deliberately

Historical versions, downloads and citations use current access. Changing a Document's audience requires a human managing every group in the current or proposed allowlist. Each manager must also be an ordinary member of that same group. Reading a document alone does not permit sharing it.

Group deletion is blocked by Document or active upload/source references. Resolve each reference using the owning operation's permissions. Deleting a group must not cascade into document deletion or silently replace defaults.

## Follow erasure

1. Require Delete documents on every group in the current nonempty allowlist. Add and Update are separate permissions.
2. Record a scoped deletion marker under current authority. Block protected access and publication before physical cleanup begins.
3. Use the existing durable, reference-aware cleanup workflow. Preserve enough progress to resume after interruption without creating another deletion engine.
4. Keep late jobs from republishing erased inputs. Shared vectors needed by other versions follow their exact reference rules.
5. Report affected historical inputs as unavailable rather than silently substituting another corpus or reconstructing deleted evidence.

A retention pin means admitted or retained work still needs an artifact. Ordinary expiry respects pins. Explicit erasure can invalidate them. Immutability preserves identity and provenance, not content forever.

For Evaluation, source replacement must not retarget an old expected passage. Source erasure can make questions, references or protected evidence unavailable.

## Ownership and failure behavior

Removing Alice's account does not itself delete shared project documents. Application-account retirement preserves required attribution without reassigning its actions to a human.

Whole-project deletion has its own human-only authority and scope. It can erase project-owned private content without granting the deleter reading rights. Individual-resource deletion in a surviving project keeps its ordinary checks.

After a deletion marker commits, an interrupted cleanup remains blocked and resumable. One observation of physical absence does not establish final cleanup when delayed writes are possible. Indexing owns numerical tombstones and completion barriers. Knowledge must not declare them complete merely because document admission is blocked.

## Status and sources

The erasure and audience rules are accepted design. Exact retention periods and every cleanup/storage protocol are not qualified by this explanation. Use existing code and attributed evidence when answering what works today.

- [Retention and deletion](../../../../docs/development/retention-and-deletion.md), [blocking before cleanup](../../../../docs/development/retention-and-deletion.md#operation), [Knowledge sharing](../../../../docs/development/knowledge-lifecycle.md) and [Access group managers](../../../../docs/development/access-control.md#group-managers).
- [Group relationship constraint](../../../../docs/development/data-model.md#group-manager-membership-constraint), [protected evaluation history](../../../../docs/development/evaluation.md#history) and [Indexing retirement](../../../../docs/development/indexing.md#retirement).
- [Maintainer lifecycle checks](../../../../docs/development/knowledge-lifecycle.md#maintainer-checks) cover replacement, retry, changed audiences and deletion races.
