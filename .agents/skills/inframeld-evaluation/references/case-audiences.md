# Protect evaluation cases and imported content

<a id="protect-evaluation-cases-and-imported-content"></a>

Alice approves HRPrivate as an import audience. SupportBot may import cases into that saved protection without gaining authority to widen it. Linking a source adds its current protection rather than replacing the case audience.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="case-audiences"></a>

<a id="alice-approves-an-audience-and-supportbot-imports-cases"></a>

### Alice approves an audience and SupportBot imports cases

Alice has `manage-evaluation-case-audiences` on the HR Pipeline and manages HRPrivate. She saves HRPrivate as its nonempty, project-local future-import audience. SupportBot has `edit-evaluation-cases` on that Pipeline and imports questions/reference answers into this saved protection. The backend protects content immediately, including unresolved cases without linked sources. The import grant does not give the bot audience administration or document-reading access.

An application import must use the saved current human-approved audience. An explicit different audience is denied, not ignored or substituted. Review and capture the audience's identity/revision with the import. Recheck current binding, project/group state and required authority before saving. Changed reviewed state conflicts rather than broadening disclosure. Human imports may explicitly review another protected destination audience only with the same Pipeline audience authority and group-management checks.

Changing the default from HRPrivate to SupportKnowledge requires the Pipeline action and management of every group in the authoritative old and proposed audiences, including removed, retained and added groups. Both audiences must remain nonempty and project-local. The default change affects future imports only. Existing cases retain their saved protection until a separately reviewed change identifies exact cases/revisions and old/new audiences. Save the protected change, expected-state checks and audit together using normal Access coordination. Do not infer management from edit/review grants or imported metadata.

Bob needs `view-evaluation-cases` on the Pipeline and access through the case's current audience to read it. Linking an HR-only source adds current source access: changing the case audience to SupportKnowledge cannot expose that source-backed case to a Support-only reader. Keep protection through edits/reimport and protect history, results and unresolved excerpts under the same current checks. Group deletion must not leave a live default or stored case protection dangling. Relevant references must first be handled through their authorized lifecycle. Source erasure covers derived protected case content under the existing erasure rules.

New/changed content creates unreviewed revisions. Audience administration is not acceptance and never imports a foreign review as local authority. Exact content-review behavior beyond these invariants remains with the case contract. This audience decision does not invent a new review-reset rule. [ADR-0061](../../../../docs/adr/ADR-0061-control-evaluation-audiences-through-pipeline-authority.md) records the choice. [Logical records](records.md#evaluation) and [Access operation contracts](../../inframeld-access-models/references/grant-administration.md#operation-contracts) distinguish accepted meaning from pending physical/wire schemas.

<a id="retained-logical-information"></a>

## Retained logical information

| Information | Owner and constraint |
| --- | --- |
| Imported case audience and source mapping | Store nonempty project-local protection immediately, including unresolved content. A Pipeline has a human-managed saved future-import audience and revision. Applications capture that current binding, while existing cases retain their saved audiences. Explicit changes identify exact cases/revisions and authoritative old/new groups. Verified source-version/artifact/span mapping adds current source checks. New/changed content is unreviewed. Unchanged imports retain identity/review. Group references remain protected lifecycle dependencies. Physical fields/tables and wire spellings remain unimplemented. |

<a id="authorization-failure-scenarios"></a>

## Authorization failure scenarios

| Situation | Required outcome |
| --- | --- |
| SupportBot imports HR cases into the saved HRPrivate audience before source linking. | Store protected unreviewed content immediately. Audience override is denied, linked sources later add checks. |
| Alice changes the import default from HRPrivate to SupportKnowledge. | Require Pipeline audience authority and management of both groups. Existing cases retain HRPrivate. |
| The selected audience/reviewed revision changes before import or audience save. | Reject stale reviewed state. Never widen or substitute the audience silently. |
