# Present an explicit before-and-after review

Alice changes Production’s mode. Show current and proposed values clearly in terminal, plain text and structured output. A displayed difference is not permission to apply it or a guarantee that state cannot change afterward.

<a id="change-review"></a>

<a id="make-the-changed-state-visually-explicit"></a>

### Make the changed state visually explicit

Alice's working configuration is revision 17. She proposes enabling Ettin 32M and increasing retrieval from 20 to 30 passages. Review the relevant fields in aligned **Current / Proposed** rows before saving. The proposed side is not already saved, does not reserve a revision number, and does not change production. Only a confirmed save creates a new current configuration revision. Normal authority, supported settings and expected-revision checks still apply.

Use [the shared delta contract](#cli-change-presentation): red struck-through old values, an arrow, green new values and neutral unchanged information, with explicit headings and a plain-text fallback. The examples in structured change presentation are illustrative, not implemented interfaces.

| Situation | What the user sees | What the operation does |
| --- | --- | --- |
| Settings changed after review but before Build admission | **Reviewed / Now**: configuration `17 -> 18`, followed by "Build not started: settings changed." | Reject the stale decision. Obtain fresh review instead of silently updating revisions or accepting newer inputs. |
| Working settings changed after Build was admitted | **Before / Now**: saved configuration `17 -> 18`. Separately, **This build: 17 (unchanged)**. | Keep admitted configuration/corpus inputs fixed. Ordinary current authority, dependency and shared-connection checks still apply. |
| Automatic changed to Manual before conditional publication | **Before / Now**: release mode `Automatic -> Manual`. If preparation succeeds, "Version v4 is ready. Not released." Show **Live version: v3 (unchanged)** only when that is confirmed. | The old publication authority is invalid. Keep useful ready output without publishing or reviving the request after an off/on switch. |
| Pipeline settings are being edited | **Current / Proposed** rows for the selected supported fields. "Not saved. The live deployment is unchanged." | Save only after the ordinary explicit decision and current checks. No implicit query, evaluation, Build or release follows. |

These examples assume the separately named facts are available to the caller. If current state is unavailable, report that limitation instead of displaying a guessed "Now" value. A lost acknowledgment does not justify a green completed-change row. Recover the original operation first. Likewise, comparing a ready v4 with live v3 is not evidence that traffic moved from v3 to v4. Label a proposed release as proposed until Releases confirms it.

Use existing authorized observations and normal bounded status/inspection, not a new subscription or change-history platform. The CLI presents these observations. Owning domains define admission and revision contracts. Display semantics and terminal fallbacks still require qualification.

<a id="cli-change-presentation"></a>

<a id="present-changes-as-labelled-before-and-after-values"></a>

### Present changes as labelled before-and-after values

Alice reviews configuration 17, but the current saved configuration is now 18. A small aligned row, `Configuration  17 -> 18`, is easier to scan than a paragraph. Its heading must say **Reviewed / Now**, because Alice's command did not make that change. The structured change presentation contract selects this shared CLI presentation for supported change reviews and observed changes. It is not a new diff service or data framework.

Use a field label, the old value, an arrow and the new value. In a capable interactive terminal, render the old value red with strikethrough and the new value green. Green means **new**, not better, approved, safe or successfully applied. Keep unchanged values neutral and identify them as unchanged when their stability matters. A ready version that has not been published cannot appear as a completed live-version delta.

| What the view describes | Column labels | Meaning |
| --- | --- | --- |
| Proposed mutation, including a dry-run | **Current / Proposed** | No change has been applied by this view. |
| Confirmed change | **Before / Now** | The named state actually changed. Only claim effects the backend confirmed. |
| Stale decision compared with current state | **Reviewed / Now** | The reviewed state is no longer current. Fresh review is required. |

The column labels and field identity carry the meaning without styling. For example, a saved configuration changing from 17 to 18 does not change an already admitted build's captured configuration 17. Show that build input separately and neutrally. [Pipeline change examples](#change-review) apply this distinction to edits, Build and publication.

- Use the same visual convention across configuration, model-connection, import, policy and release change views where their owning contracts provide authorized old/new facts. Do not create one-off renderers with competing meanings or add new backend history solely to show a delta.
- Respect `NO_COLOR`, `--no-color`, `TERM=dumb` and non-terminal output. Omit unsupported styling and use a plain `->` with explicit labels when needed. Never depend on color or strikethrough alone. JSON has no presentation ANSI codes or decorative arrows. Preserve the same permitted values and proposed/observed meaning under the reviewed machine contract.
- Show the affected resource and change scope. Keep version identity, configuration revision and release mode distinct. Display only actually known values. Unavailable old state is not an empty value, zero or evidence that nothing changed.
- Wrap or stack long rows in narrow terminals while keeping labels attached to their values. For long text or many changes, use bounded detail/ordinary inspection rather than silently hiding a material difference. This does not add another editor or a new storage system.
- Exclude secret values from both sides and from JSON, logs and artifacts. Retain current authorization and erasure for other protected content. Render untrusted text safely. Input control characters cannot insert styling or impersonate a confirmation. Showing a difference is neither authorization nor consent to apply it. The [machine change view](#machine-change-views) and [common framing](cli-output-and-automation.md) are accepted. Command-specific typed values and terminal behavior still require implementation and qualification. Feature commands must consume that presentation and qualify its behavior. The following client-owned representation adds no backend endpoint, physical record, automatic polling subsystem or permission. This pass documents accepted design, not tested terminal compatibility. [clig.dev](https://clig.dev/#output) supplies the output/color guidance. The specific red-strikethrough/green convention is Inframeld's accepted choice.

## Machine change views

The client-owned change-view representation was accepted on 2026-10-29 through the approved joint #124/#156 specification plan. It is design, not an implemented field model or a backend history API.

A command-specific typed `data` object may contain `changes`, a bounded array of views. Each view has `kind` (`proposed`, `confirmed` or `stale`), `resource` (the permitted typed resource reference) and `fields` (typed field changes). Kind maps respectively to Current/Proposed, Before/Now and Reviewed/Now. Keep admitted build inputs or other unchanged identities separate from a changing live/configuration value.

Each field has a stable `field` identifier and `before`/`after` observations. Each observation is one of `{"known": false}` or `{"known": true, "value": ...}`, where the command defines the permitted value type. A known `null`, empty string, zero or false is not an unknown observation. Omit forbidden fields entirely. Never replace a secret with either a real value or a distinguishable hint.

The following example belongs to this reference's `machine-change-views` section. Its leaf resource/field identifiers illustrate command data, not published backend wire names. It describes a proposal, not an applied revision:

```json
{
  "kind": "proposed",
  "resource": { "configurationId": "configuration-example" },
  "fields": [
    {
      "field": "retrievalLimit",
      "before": { "known": true, "value": 20 },
      "after": { "known": true, "value": 30 }
    }
  ]
}
```

Confirmed views require authoritative evidence of the named effects. Stale views compare reviewed state with a permitted current observation and require fresh review before a new mutation. Unknown old state cannot become a confirmed change from zero. The command's typed field catalogue defines semantics, bounds and allowed values. This is not an arbitrary JSON-map renderer or a requirement to record additional backend state.
