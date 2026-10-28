# Test behavior and explain the contract

<a id="test-behavior-and-explain-the-contract"></a>

Alice adds a command that waits for a build. A useful test proves how the requested wait ends when the build fails. A test that merely checks a module name cannot demonstrate that outcome. This reference owns the shared TDD and documentation contract. Language-specific test organization and examples belong to [Python Standards](../../inframeld-python-standards/references/testing-and-documentation.md) and [Rust Standards](../../inframeld-rust-standards/SKILL.md).

<a id="behavioral-tdd"></a>

## Behavioral TDD

For new behavior and bug fixes, follow this sequence:

1. Establish only the public symbols, signatures and lifecycle shape needed to import and execute the test. The scaffold is an API outline and implements none of the behavior under test. Add only a real required seam.
2. Write the behavioral test against those symbols.
3. Run it and require failure for the expected behavioral reason. Import, compilation or collection errors mean the seam is incomplete. Add only the missing symbol/signature and rerun.
4. Implement the smallest real behavior. Run the focused test, then the relevant suite.
5. Refactor while tests remain green. Do not smuggle behavior into scaffolding or add interfaces for speculative future services.

Test actual product behavior, contracts and integrations. Do not add architecture/import-boundary tests, dependency-rule fixtures, composition-root construction tests, naming checks or similar repository-setup enforcement. The developer guards organization manually. A negative test must distinguish a rejected operation from a partial mutation or disclosure where that boundary matters.

Use the [Testing skill](../../inframeld-testing/SKILL.md) when choosing layers, dependency isolation or interpreting evidence. Controlled collaborators can demonstrate decisions and interactions, not an unexecuted database/provider guarantee. Type-compatible authorization cannot establish ordering before disclosure or mutation. Qualified SDK fixtures cannot establish a complete product workflow.

Keep verification proportional to the change. Run focused behavior tests and required checks. Repeat or broaden them when new changes, failures or unresolved concerns justify it. Report personally executed, developer-reported, skipped, cached and unavailable checks accurately. Documentation-only work requires editorial checks rather than application-suite execution.

<a id="purpose-before-implementation-detail"></a>

## Purpose before implementation detail

Start useful code documentation with purpose and the behavior's context. Preserve trust assumptions, caller prerequisites, result meaning, expected failures, non-obvious invariants, I/O/state changes and resource ownership where a maintainer would otherwise need to investigate. Keep ordinary propagation and details already obvious from names/types out of repetitive prose.

Shared contracts belong to the declaring interface or capability. Implementations add relevant details without repeating that contract. Explain what a transfer record establishes and what remains unchecked. Keep longer workflows in their owning references rather than copying them into each method.

Prefer compact, value-based documentation over fixed function/docstring lengths or blanket declaration coverage. Document scenario and fixture details that explain behavior, without narrating every assertion or repeating signatures. The language guide owns syntax and declaration-specific conventions.

Use no semicolons or em dashes in prose, comments or docstrings. Use separate sentences or a normal hyphen. This wording rule does not constrain punctuation required by source-language syntax.

## Complete, source-backed examples

Identify the exact file path and whether a proposed snippet is a complete new file, replacement or insertion beside a named line. Include imports, the surrounding declaration and configuration needed to apply it. Separate multi-file examples and explain their connection. Label illustrative pseudocode and copyable code distinctly.

For inspected teaching excerpts, name the source and scope rather than implying the excerpt replaces a complete module. Preserve relevant fixture declarations, permission checks, transaction ownership, failure behavior and valid exceptions. Do not use unexplained ellipses or omit safeguards from an example presented as a complete use case.

An inspected representation is not a universal naming convention. Apply language-specific guidance to the example, and keep accepted design, inspected implementation and executed checks separate. Source inspection alone cannot establish runtime qualification.
