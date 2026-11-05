# ADR-0129: Bound numeric revisions to the JavaScript safe integer range

**Status:** Accepted

**Date:** 2026-11-05

## Context and Problem Statement

Alice reads Project Access revision `42` and submits it as `expectedAccessRevision`. The server compares it with current state before saving her change. Clients must preserve the exact value so an outdated request cannot accidentally match a different revision.

The API previously advertised revisions through `2^63 - 1`. JavaScript's ordinary `number` type cannot distinguish every integer in that range. The current TypeScript client uses generated numeric models and response validation, so the full advertised range is not interoperable. Some physical counters also used PostgreSQL `INTEGER`, which cannot store the full advertised range.

On 2026-11-05 the developer selected the JavaScript-safe numeric bound and authorized its implementation across the codebase. This supersedes the earlier approved but unimplemented TypeScript `bigint` proposal for revision fields. It also narrows the representation of the revision guards in [ADR-0022](ADR-0022-coordinate-access-writes-by-project-with-scope-revisions.md), without changing their coordination or authorization protocol.

## Considered Options

- Preserve full signed 64-bit JSON numbers and introduce exact TypeScript `bigint` parsing, serialization and generated models. This preserves the previous range but requires additional client and generator behavior.
- Expose string-valued revisions. This avoids JSON number precision loss but changes request, response and caller types, including the existing numeric receipt-integrity check.
- Keep JSON numbers and restrict revisions to the exact integer range shared by the selected clients. This preserves their current public representation and avoids a special numeric transport.
- Use an arbitrary smaller cap, such as one million. This adds an earlier lifetime limit without improving interoperability over the safe-integer bound.

## Decision Outcome

Numeric product revisions use the inclusive range **0–9,007,199,254,740,991** (`2^53 - 1`). A particular operation may require a positive revision. Preserve those existing minimums. JSON revisions remain integer numbers, with native OpenAPI declaring `type: integer`, `format: int64` and the actual minimum and maximum. Query parameters retain the operation's strict decimal parsing.

Use exact integer representations at every boundary. PostgreSQL stores participating counters in `BIGINT` columns with the same effective bounds. Request, response, retained-result and conditional-write handling must agree. A stored 64-bit column does not permit the API to exceed the smaller accepted range.

| Language or store | Required representation |
| --- | --- |
| JavaScript / TypeScript | `number`, validated as a safe integer in the accepted range. |
| Python | `int`, with explicit range and strict-type validation at the relevant boundary. |
| Rust | `i64` or another explicitly checked integer type that covers the accepted range. Existing generated revision fields remain `i64`. |
| Java / Kotlin | `long` / `Long`, with range validation. |
| C# | `long`, with range validation. |
| Go | `int64`, with range validation. |
| PostgreSQL | `BIGINT`, constrained to the accepted range. |

This is a common interoperable contract for these types, not a claim that every language's type named `int` can hold it. Java/C# `int`, Rust `i32` and a 32-bit Go `int` are too small. Floating-point types with less than binary64 precision are also unsuitable.

At the maximum, reject a change that requires a further increment before committing its effects. Never wrap, reset or clamp a revision. An unchanged operation may retain its current revision. An authorized exact replay returns its original retained result without incrementing again. Current authorization, original request identity, scope, conditional updates and transactional audit remain required. Preserve the maintained CLI receipt check that a successful changed admission advances the revision by exactly one.

The [shared numeric revision contract](../../.agents/skills/inframeld-application-contracts/references/http-mcp-and-generated-clients.md#numeric-revisions) owns the current transport and failure rules. Domain owners retain what each revision identifies and when it advances. This decision does not recast immutable hash/UUID revision identities, credential generations, advisory-lock keys, byte quantities, money or provider-duration limits as numeric product revisions.

## Consequences

The selected clients can round-trip every accepted revision through ordinary JSON. The TypeScript revision model remains `number`, and revision support no longer needs the proposed `bigint` parser or serializer work. This conclusion does not establish that unrelated wide numeric quantities need the same representation.

Existing 32-bit counters require a forward migration. Narrowing an existing wider persisted revision requires checking existing data and rejecting an unsafe upgrade rather than truncating values. Downgrading widened counters must likewise fail when their values cannot fit the previous storage type. Regenerate native OpenAPI and all three clients together, and qualify boundary values, exhausted changed writes, unchanged operations and original-result replay. The accepted decision alone supplies no test or platform result.

## Links

- [ECMAScript `Number.MAX_SAFE_INTEGER`](https://tc39.es/ecma262/multipage/numbers-and-dates.html#sec-number.max_safe_integer) and [RFC 8259, section 6](https://www.rfc-editor.org/rfc/rfc8259.html#section-6).
- [Rust `i64::MAX`](https://doc.rust-lang.org/std/primitive.i64.html#associatedconstant.MAX), [Python numeric types](https://docs.python.org/3/library/stdtypes.html#numeric-types-int-float-complex), [Java integer types](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.1), [C# integral types](https://learn.microsoft.com/en-us/dotnet/csharp/language-reference/builtin-types/integral-numeric-types) and [Go numeric types](https://go.dev/ref/spec#Numeric_types).
- [Access grant contracts](../../.agents/skills/inframeld-access-models/references/grant-contracts.md) and [retry versus competing-edit behavior](../../.agents/skills/inframeld-application-contracts/references/idempotency-and-replay.md#revisions).
