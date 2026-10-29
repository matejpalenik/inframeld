# Write from the reader's task

Alice does not need an introduction to the transport adapter before checking whether her request was accepted. She needs to know which details to retain, what lookup can tell her and what to do with the result. Structure the page around this decision. Explain implementation details only when they change her action or interpretation.

This guide adapts observable techniques in public OpenAI documentation to Inframeld. It is an original editorial guide. It does not copy OpenAI text or assume that Inframeld has OpenAI's credentials, publishing model or retry behavior.

## Address the reader clearly

Use second person for instructions: “Keep the original request key.” Use a named system actor for explanations: “The server checks your current permission before returning a retained result.” Choose imperative verbs for actions and factual statements for behavior. Avoid switching between “you”, “we” and an imaginary administrator without introducing who acts.

Prefer familiar verbs such as create, send, keep, check and return. Replace “utilize”, “facilitate” and “leverage” with the actual action. Keep a technical word when it names a real concept or contract, then explain it at its first useful appearance. Avoid promotional claims, reassurance without evidence and statements about how easy the task is.

Use connected paragraphs that develop one idea. A paragraph usually starts with the purpose or conclusion and then supplies the condition or explanation needed to understand it. Do not enforce an arbitrary sentence length or reading grade. A short sentence that drops a condition can be less clear than a longer precise one.

State the subject and consequence. “Changing the selected account changes the target for later commands” is more useful than “Context may be affected.” Prefer active voice when the actor matters. Passive voice is acceptable when the actor is irrelevant, but not when it hides who authorizes, stores, retries or deletes something.

## Introduce concepts in causal order

Start with the problem and introduce a term when it helps explain the next step. For example:

> A request can be accepted even when your client never receives the response. Admission is the point where the server accepts the action for processing. Losing the response does not reverse that acceptance. Keep the original context so you can check the retained result without submitting a new action.

This explains why admission matters before asking the reader to remember the term. It preserves the distinction between server acceptance and client observation. It does not imply that every request is asynchronous or that lookup is available for every operation.

Use one small example through an explanation. Alice can request a change and SupportBot can act under its own authority, but introduce the change of actor explicitly. Do not use a different resource, identifier and permission model in every paragraph. Example names should make relationships visible. Follow the accepted [resource identity guidance](../../inframeld-architecture/references/resource-names-and-identity.md) when names, display names and IDs matter.

Preserve exact wire names inside code. If the implementation returns `accepted_asynchronous`, explain the meaning in prose without renaming the value in JSON. Separate a human label from a machine identifier. Never silently substitute the current default account or target for retained request context.

## Put the useful path first

A task page opens with an outcome and the condition where the reader should use it. State required setup before the first command. Put optional alternatives after the smallest complete path. Explain a default where it affects what happens. Avoid a long conceptual introduction before the reader can make progress.

Each step should have a reason when it is not obvious, a concrete action and an observable result. Name the file or environment before a code block. Explain the output immediately after it. Put warnings beside the action they constrain. Do not collect important permission or retry conditions in a remote “edge cases” section.

Choose headings that answer a question or name an action: “Keep the original context”, “Check the result” or “When access changes”. Use a table to compare parallel outcomes or fields. Use numbered steps for a sequence. Avoid turning a connected explanation into a long list of isolated facts.

Link with descriptive text: “Read the current permission requirements” instead of “click here”. Link to a focused explanation when readers need more depth. A user should not have to inspect a service implementation or ADR to complete a documented task.

## Explain failures without inventing certainty

Separate a successful inspection request from the outcome of the original action. A successful lookup response can report an unresolved result. Explain what each result establishes and what it leaves unknown. Name the next supported action, including cases where the reader must stop and retain evidence.

An error explanation should connect cause, consequence and next action. Do not recommend retries mechanically. A lost response, changed permission or expired result can require different recovery. Preserve whether effects may already exist and which original context must be reused. Never turn `unresolved` into “the action failed” or “nothing happened”.

Permission and privacy conditions belong in the normal explanation when they affect the returned information. Current permission checks are not optional troubleshooting details. A response that intentionally reveals little must not be described as proof that no matching request exists.

## Edit for concrete meaning

These are original Inframeld examples, not replacements for inspected endpoint documentation.

| Before | After | Why |
| --- | --- | --- |
| Utilize the lookup facility to ascertain admission status. | Check whether your original request was accepted. | Names the reader's purpose with familiar words. |
| The resultant authority-binding mismatch precludes historical resolution. | The result is unresolved. It does not tell you whether a retained request exists. | Explains the observable limit without exposing private state. |
| On timeout, retry the operation. | If you lose the response, keep the original request context and follow the documented recovery path. | Avoids implying that a new write is safe. |
| The secure interface supports all SDKs. | The selected Python, TypeScript and Rust clients use the delivered OpenAPI contract. Requests still require current permission. | Replaces broad reassurance with a checkable claim. |
| As can be seen above, the request was processed. | The response includes the original operation ID. | Describes the evidence without claiming more than it shows. |

Read the page aloud during the final edit. Remove repeated setup, vague transitions and claims that a reader cannot verify. Preserve exact conditions and meaningful exceptions. Use no semicolons or em dashes in prose, comments or docstrings.
