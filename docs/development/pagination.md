# Cursor pagination

Use this reference when a list is too large to return at once. A **cursor** marks where the next page should begin. [ADR-0005](../adr/ADR-0005-use-bounded-cursor-pagination-for-lists.md) explains the choice, [API contracts](api-contracts.md) covers the surrounding API, and [documentation maintenance](documentation-maintenance.md) explains reference ownership.

> **Status:** The shared parameter and response models exist. Each list endpoint still owns the meaning of its cursor and its permission checks.

A request sends `limit` and, for a later page, an opaque `cursor`. The response contains `items` and `nextCursor`. Clients pass the cursor back without interpreting or changing it. A null `nextCursor` means the list has ended.

[pagination.py](../../apps/backend/src/inframeld_backend/shared/http/pagination.py) defines `PaginationQuery` and `PageResponse[Item]`. The exact limits are:

| Field | Rule |
| --- | --- |
| `limit` | Defaults to 25. Allowed range: 1–100 inclusive. |
| `cursor` | If supplied, must be nonempty, at most 1024 characters, and use unpadded URL-safe base64 characters. |

Invalid query values return the established RFC 9457 validation problem.

## Rules for an owning list endpoint

1. Check identity and permission on every page. Having a cursor never grants access.
2. Apply the caller's project or resource restrictions and filters again, including when a cursor is present.
3. Use a predictable order with a unique final field to break ties, such as `created_at DESC, id DESC`. Resume after both values.
4. Decode and check the cursor against this endpoint's ordering, filters, and permitted scope. Return a safe 422 problem for malformed or incompatible contents. Valid characters alone do not prove a valid cursor.
5. Fetch at most `limit + 1` matching records to discover whether another page exists. Return at most `limit` items, and provide `nextCursor` only if there is another page.
6. Keep credentials, private content, and other sensitive values out of cursors. Base64 is encoding, not encryption. Do not log the raw cursor.

Declare `PageResponse[Item]` and the applicable error responses in OpenAPI. The feature chooses its cursor contents and database query. This shared contract does not prescribe them.

For example, two uploads may have the same `created_at` time. Their unique IDs decide which comes first. Saving only the timestamp in the cursor could skip one upload when Alice asks for the next page.
