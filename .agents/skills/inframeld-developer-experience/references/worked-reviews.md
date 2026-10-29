# Calibrate findings with concrete journeys

These original examples teach review reasoning. They are illustrative observations, not claims about defects currently present in Inframeld. Inspect the actual implementation and accepted contract before reporting a finding. Use the standard Review report for a real assignment.

## Machine output includes human progress

Alice runs an implemented command in JSON mode and pipes stdout to a JSON parser. A controlled fixture returns one result, but the command prints a progress sentence followed by the object on stdout. The parser fails before reaching the object.

Weak review: “The output should feel more like Stripe. Add a quiet mode and a new renderer abstraction.”

Useful review: “P2: JSON output includes a progress line. In the supported non-TTY JSON invocation, stdout contains human text before the JSON object, so the documented parser cannot consume the result. Keep the machine payload on stdout and route diagnostics according to the accepted output contract. Add a focused behavioral check of that invocation.”

The useful review identifies the developer task, concrete failure, owning contract and smallest remedy. It does not require a new output framework or copy another product's flags. The severity depends on affected usage and the accepted contract, not on this example's label alone.

## A timeout is presented as a failed write

Alice sends a change and loses the response after the server might have accepted it. An example catches the transport exception and says “The action failed. Retry with a new key.” The server's actual outcome is unknown.

Weak review: “Improve the error handling.”

Useful review: “P1: the recovery example can duplicate a write. A response timeout does not establish rejection. Recommending a new key can submit a distinct action after the first was accepted. Preserve the original request context and describe the supported observation or recovery path. Keep unknown effects explicit.”

This is a concrete correctness concern. It does not imply that every timeout has effects or that all operations support the same lookup. The reviewer must inspect the actual operation and qualify the recommendation.

## An intentionally limited result is treated as missing information

The accepted lookup result can be `{"outcome":"unresolved"}` for several cases, preserving privacy. A reviewer suggests adding a reason such as “wrong account” to every response so the developer can debug faster.

Reject that suggestion when the accepted contract intentionally hides whether retained history exists. Better diagnostics cannot weaken the current authority or privacy boundary. The useful review checks that the guide explains the limit and provides a safe next step. It does not require the API to disclose the hidden cause.

## A generated return type is hidden by an invented helper

A tutorial shows `result.is_success()` and `result.operation_id`, but the inspected generated Rust API returns an enum whose variants carry different data. The helper does not exist.

Weak review: “Add a universal response facade across all SDKs.”

Useful review: “P2: the copyable Rust example does not compile against the selected generated SDK. Use the actual enum variants and access the operation ID only in the variant that provides it. Keep the Python and TypeScript examples behaviorally equivalent using their native types.”

The remedy fixes the example and preserves generator ownership. A facade might be justified by a broader supported need, but a single tutorial mismatch does not establish that need.

## Valid exceptions and non-findings

An internal-only helper change can need no user documentation when public behavior is unchanged and the reason is recorded. A CLI foundation issue can correctly deliver offline help without delivering future account workflows. A command with no meaningful progress need not add a progress renderer. A generated package can be useful locally before publication if setup is accurate.

Plain human output can differ from another CLI while remaining clear and consistent. A privacy-preserving unresolved response can be intentionally sparse. A non-interactive path can reject an unsafe operation rather than silently choose a target. These are not defects merely because they differ from a preferred product.

If the scoped journey has no material findings, say so. Keep optional P3 ideas separate. Do not keep inventing changes to reach a numerical ten, and do not turn a narrow read-only assessment into authority to publish comments or edit the branch.
