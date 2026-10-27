# Read one bounded authorized page

<a id="read-one-bounded-authorized-page"></a>

Alice lists project members. The response contains one bounded page and an opaque cursor for continuing. The cursor identifies a position, not permission to see later results.

> **Status:** accepted behavior is stated separately from proposed representations and qualification work. Existing Python types, generated OpenAPI and migrations own implemented shapes. Pending decisions are not accepted by this reference.

<a id="cli-list-contract"></a>

<a id="return-one-bounded-page-unless-traversal-is-explicit"></a>

### Return one bounded page unless traversal is explicit

For example, `pipeline list --search contracts --limit 3` returns up to three visible matching resources, not all results or the first three rows before local filtering. Ordinary lists use the existing pagination contract: default 25, limit 1-100 and an opaque continuation cursor. Human and JSON output use identical filtering/page semantics. Piping output or choosing JSON does not fetch every page.

The backend applies supported filters and current access before pagination. `--search` covers the resource's supported Name/Display name matching, not document-body/semantic search or a model call. Search results do not turn Display names into exact selectors. Each owner specifies matching and stable order with a unique tie-breaker. No generic search engine is introduced.

Show how many items were returned and whether more exist. Show totals only when an authorized authoritative count exists. A continuation example preserves effective context, filters/order and uses safe shell quoting for the actual cursor. The CLI neither decodes nor logs raw cursor values. Cursors contain no secrets, grant no authority and must be validated against endpoint/filter/scope. Changed filters begin a new traversal. Malformed/expired/incompatible cursors fail rather than becoming an empty success.

`--all` explicitly follows matching pages within declared resource/time bounds. `--limit` remains per-page size. Freeze context and query inputs for traversal and check current backend authority for every page. This is not a snapshot transaction, bulk mutation or request for hidden/archived data. Concurrent changes can affect later pages under the owning contract.

Permission loss, failed requests or reaching a traversal bound produce an incomplete nonzero outcome, retaining parseable permitted partial/completion information. Never silently truncate while claiming all, treat transport denial as an empty list or concatenate undocumented JSON page objects. Default JSON retains `items`/`nextCursor` meaning with null at the end. Exact aggregate/stream schema and bounds remain work. Dry-run describes traversal without fetching requested pages.

Qualification includes empty results, ties, page-boundary filtering, rename/deletion, invalid cursors, changed permissions, interrupted traversal, JSON/human parity, bounded memory/time and no model calls. This acceptance contract does not claim every list endpoint exists.

<a id="cursor-pagination"></a>

## Cursor pagination

Use this reference when a list is too large to return at once. A **cursor** marks where the next page should begin. [ADR-0005](../../../../docs/adr/ADR-0005-use-bounded-cursor-pagination-for-lists.md) explains the choice, [API contracts](http-mcp-and-generated-clients.md) covers the surrounding API, and [documentation maintenance](../../../../docs/development/documentation-maintenance.md) explains reference ownership.

> **Status:** The shared parameter and response models exist. Each list endpoint still owns the meaning of its cursor and its permission checks.

A request sends `limit` and, for a later page, an opaque `cursor`. The response contains `items` and `nextCursor`. Clients pass the cursor back without interpreting or changing it. A null `nextCursor` means the list has ended.

[`pagination_query.py`](../../../../apps/backend/src/inframeld_backend/shared/http/requests/pagination_query.py) defines `PaginationQuery`. [`page_response.py`](../../../../apps/backend/src/inframeld_backend/shared/http/responses/page_response.py) defines `PageResponse[Item]`. The exact limits are:

| Field | Rule |
| --- | --- |
| `limit` | Defaults to 25. Allowed range: 1–100 inclusive. |
| `cursor` | If supplied, must be nonempty, at most 1024 characters, and use unpadded URL-safe base64 characters. |

Invalid query values return the established RFC 9457 validation problem.

<a id="rules-for-an-owning-list-endpoint"></a>

## Rules for an owning list endpoint

1. Check identity and permission on every page. Having a cursor never grants access.
2. Apply the caller's project or resource restrictions and filters again, including when a cursor is present.
3. Use a predictable order with a unique final field to break ties, such as `created_at DESC, id DESC`. Resume after both values.
4. Decode and check the cursor against this endpoint's ordering, filters, and permitted scope. Return a safe 422 problem for malformed or incompatible contents. Valid characters alone do not prove a valid cursor.
5. Fetch at most `limit + 1` matching records to discover whether another page exists. Return at most `limit` items, and provide `nextCursor` only if there is another page.
6. Keep credentials, private content, and other sensitive values out of cursors. Base64 is encoding, not encryption. Do not log the raw cursor.

Declare `PageResponse[Item]` and the applicable error responses in OpenAPI. The feature chooses its cursor contents and database query. This shared contract does not prescribe them.

For example, two uploads may have the same `created_at` time. Their unique IDs decide which comes first. Saving only the timestamp in the cursor could skip one upload when Alice asks for the next page.
